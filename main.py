"""
BZB Gear AI Advisor — FastAPI server
Run: uvicorn main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
import os
import threading
from dotenv import load_dotenv
load_dotenv()

import truststore
truststore.inject_into_ssl()

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional

from api.models import SessionState, SessionUpdate, Product, RecommendRequest, RecommendResponse
from api.sessions import create_session, get_session, update_session
from api.layer1 import search_products, get_product
from api.layer2 import get_chunks_for_candidates, semantic_search_products
from api.layer3 import get_recommendation
from api.universal_engine import get_universal_recommendation, get_flow_a_recommendation, parse_approaches
from api.chat import run_chat_turn, get_opening_message
from api.chain import build_chain, chain_to_text
from api.db import get_conn, row_to_dict, init_chat_state_table, save_chat_state, load_chat_state

init_chat_state_table()

app = FastAPI(
    title="BZB Gear AI Equipment Advisor",
    description="Three-layer RAG system for AV equipment compatibility recommendations",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── UI ───────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def serve_ui():
    return FileResponse("chat.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    conn = get_conn()
    product_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    conn.close()

    from api.db import get_chroma
    chroma = get_chroma()
    chunk_count = chroma.count() if chroma else 0

    return {
        "status": "ok",
        "products_in_db": product_count,
        "manual_chunks_indexed": chunk_count,
        "openai_key_set": bool(os.environ.get("OPENAI_API_KEY")),
    }


# ─── Sessions ─────────────────────────────────────────────────────────────────

@app.post("/session", response_model=SessionState, tags=["Session"])
def new_session():
    """Start a new customer session. Returns session_id to use in subsequent calls."""
    return create_session()


@app.get("/session/{session_id}", response_model=SessionState, tags=["Session"])
def get_session_state(session_id: str):
    s = get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return s


@app.patch("/session/{session_id}", response_model=SessionState, tags=["Session"])
def update_session_state(session_id: str, body: SessionUpdate):
    s = update_session(session_id, body.model_dump(exclude_none=True))
    if not s:
        raise HTTPException(404, "Session not found")
    return s


# ─── Products (Layer 1) ────────────────────────────────────────────────────────

@app.get("/products", response_model=list[Product], tags=["Products"])
def list_products(
    category: Optional[str] = None,
    limit: int = Query(50, le=222),
):
    """List all products, optionally filtered by category."""
    conn = get_conn()
    if category:
        rows = conn.execute("SELECT * FROM products WHERE category=? ORDER BY id LIMIT ?", (category, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM products ORDER BY id LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [Product(**row_to_dict(r)) for r in rows]


@app.get("/products/{product_id}", response_model=Product, tags=["Products"])
def get_product_detail(product_id: str):
    p = get_product(product_id.upper())
    if not p:
        raise HTTPException(404, f"Product {product_id} not found")
    return p


@app.get("/candidates", response_model=list[Product], tags=["Layer 1 — SQL Filter"])
def get_candidates(
    session_id: Optional[str] = None,
    category: Optional[str] = None,
    min_inputs: Optional[int] = None,
    min_outputs: Optional[int] = None,
    resolution: Optional[str] = None,
    min_distance_m: Optional[int] = None,
    limit: int = Query(8, le=20),
):
    """
    Layer 1: SQL coarse filter.
    Pass session_id to auto-populate filters from session state,
    or pass filters directly as query params.
    """
    if session_id:
        s = get_session(session_id)
        if not s:
            raise HTTPException(404, "Session not found")
        min_inputs  = min_inputs  or s.num_inputs
        min_outputs = min_outputs or s.num_outputs
        resolution  = resolution  or s.resolution
        min_distance_m = min_distance_m or (s.max_distance_m if s.max_distance_m and s.max_distance_m > 10 else None)

    return search_products(
        category=category,
        min_inputs=min_inputs,
        min_outputs=min_outputs,
        resolution=resolution,
        min_distance_m=min_distance_m,
        limit=limit,
    )


# ─── Manual chunks (Layer 2) ──────────────────────────────────────────────────

@app.get("/chunks", response_model=list[dict], tags=["Layer 2 — RAG"])
def get_chunks(
    product_ids: str = Query(..., description="Comma-separated product IDs, e.g. BG-4K-88MA,BG-EXH-70C4"),
    query: str = Query(..., description="The customer question or context to search for"),
    chunks_per_product: int = Query(5, le=10),
):
    """
    Layer 2: Retrieve relevant manual chunks for given product IDs.
    Requires ingest.py to have been run first.
    """
    ids = [p.strip().upper() for p in product_ids.split(",")]
    chunks = get_chunks_for_candidates(ids, query, chunks_per_candidate=chunks_per_product)
    return [c.model_dump() for c in chunks]


# ─── Full recommendation (Layer 3) ────────────────────────────────────────────

@app.post("/recommend", response_model=RecommendResponse, tags=["Layer 3 — LLM"])
def recommend(body: RecommendRequest):
    """
    Full three-layer recommendation pipeline:
    1. Load session state
    2. Layer 1: SQL filter -> candidates
    3. Layer 2: RAG -> manual chunks per candidate
    4. Layer 3: LLM -> grounded recommendation

    Requires OPENAI_API_KEY in environment.
    Layer 2 works only after ingest.py has been run.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(400, "OPENAI_API_KEY not set")

    s = get_session(body.session_id)
    if not s:
        raise HTTPException(404, "Session not found")

    # Layer 1
    candidates = search_products(
        category=s.category_hint,
        min_inputs=s.num_inputs,
        min_outputs=s.num_outputs,
        resolution=s.resolution,
        min_distance_m=s.max_distance_m if s.max_distance_m and s.max_distance_m > 10 else None,
        signal_type=s.signal_type,
        limit=8,
    )
    if not candidates:
        raise HTTPException(404, "No matching products found for session parameters")

    # Layer 2
    query = body.question or f"{s.venue_type or ''} {s.num_inputs or ''}x{s.num_outputs or ''} {s.resolution or ''} compatibility"
    chunks = get_chunks_for_candidates(
        [c.id for c in candidates],
        query=query,
        chunks_per_candidate=5,
    )

    # Layer 3
    answer = get_recommendation(
        session_dict=s.model_dump(),
        candidates=candidates,
        chunks=chunks,
        question=body.question,
    )

    return RecommendResponse(
        answer=answer,
        candidates=candidates,
        chunks_used=chunks,
        session=s,
    )


# ─── Chat ─────────────────────────────────────────────────────────────────────

# In-memory stores keyed by session_id
_chat_histories: dict[str, list[dict]] = {}
_scenario_state:  dict[str, dict]       = {}   # _scenario_plan, _scenario_answers, _clarification_round
_pending_recs:    dict[str, dict]       = {}   # session_id -> {status, result, error}


def _fetch_products_by_skus(skus: list[str]) -> list[Product]:
    conn = get_conn()
    products = []
    for sku in skus:
        row = conn.execute(
            "SELECT * FROM products WHERE id=? AND (site_category IS NULL OR site_category != 'Discontinued') AND (stock_status IS NULL OR stock_status NOT IN ('Discontinued', 'Limited Stock'))",
            (sku,)
        ).fetchone()
        if row:
            products.append(Product(**row_to_dict(row)))
    conn.close()
    return products


class ChatMessage(BaseModel):
    session_id: str
    message: str
    selected_roles: list[str] = []


class SolutionApproach(BaseModel):
    letter: str
    name: str
    text: str
    candidates: list[Product] = []


class ChatResponse(BaseModel):
    message: str
    chips: list[str] = []
    ready_to_search: bool = False
    candidates: list[Product] = []
    recommendation: Optional[str] = None
    session: Optional[SessionState] = None
    required_roles: list[dict] = []
    solution_approaches: list[SolutionApproach] = []


@app.post("/chat/start", response_model=ChatResponse, tags=["Chat"])
def chat_start():
    """Create a new session and return the opening message with chips."""
    session = create_session()
    _chat_histories[session.session_id] = []
    _scenario_state[session.session_id] = {}
    save_chat_state(session.session_id, {}, [])
    opening = get_opening_message()
    return ChatResponse(
        message=opening["message"],
        chips=opening["chips"],
        session=session,
    )


@app.post("/chat/message", response_model=ChatResponse, tags=["Chat"])
def chat_message(body: ChatMessage):
    """Send a message and get AI response + chips. Runs full search when ready."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(400, "OPENAI_API_KEY not set")

    session = get_session(body.session_id)
    if not session:
        raise HTTPException(404, "Session not found. Call /chat/start first.")

    # Load history and scenario state — memory first, DB fallback (survives hot-reload)
    sid = body.session_id
    if sid not in _chat_histories or sid not in _scenario_state:
        db_scenario, db_history = load_chat_state(sid)
        if sid not in _chat_histories:
            _chat_histories[sid] = db_history
        if sid not in _scenario_state:
            _scenario_state[sid] = db_scenario

    history = _chat_histories[sid]

    # Add user message to history
    history.append({"role": "user", "content": body.message})

    # Store selected_roles before building session dict
    if body.selected_roles:
        _scenario_state[sid]["_selected_roles"] = body.selected_roles

    # Build full session dict including scenario planner state
    scenario_ext = _scenario_state.get(sid, {})
    session_dict = {**session.model_dump(), **scenario_ext}

    # Run LLM conversation turn
    try:
        result = run_chat_turn(
            history=history[:-1],  # history before this message
            user_message=body.message,
            session_state=session_dict,
            session_id=sid,
        )
    except RuntimeError as e:
        if "OPENAI_QUOTA_EXCEEDED" in str(e):
            return ChatResponse(
                message="OpenAI API quota exceeded — please add credits at platform.openai.com and restart the server.",
                chips=[], ready_to_search=False, candidates=[], recommendation=None, session=session,
            )
        raise

    # Persist scenario planner state in memory and DB
    for key in ("_scenario_plan", "_scenario_answers", "_clarification_round", "_selected_roles"):
        if result.get(key) is not None:
            _scenario_state.setdefault(sid, {})[key] = result[key]

    # Apply regular state updates
    state_update = {k: v for k, v in result.get("state_update", {}).items() if v is not None}
    if state_update:
        session = update_session(sid, state_update)

    # Add assistant response to history
    history.append({"role": "assistant", "content": result["message"]})

    # Flush to DB so state survives hot-reload
    save_chat_state(sid, _scenario_state.get(sid, {}), history)

    # If LLM says ready — run SQL immediately, LLM recommendation in background
    if result.get("ready_to_search") and session:
        session_dict = {**session.model_dump(), **_scenario_state.get(sid, {})}
        search_query = result.get("search_query") or body.message

        scenario_plan    = _scenario_state.get(sid, {}).get("_scenario_plan") or {}
        scenario_answers = _scenario_state.get(sid, {}).get("_scenario_answers") or {}
        flow = scenario_plan.get("flow", "solution_design")

        # ── Phase 1: SQL candidates (fast) ────────────────────────────────────
        from api.scenario_planner import _find_matching_skus_for_flow_a
        if flow in ("product_selection", "hybrid"):
            categories = scenario_plan.get("requested_categories", [])
            sql_skus = _find_matching_skus_for_flow_a(categories, scenario_answers)
        else:
            semantic_hits = semantic_search_products(search_query, n=12)
            # Exclude AV-over-IP "controller" devices when searching for PTZ controllers
            intent = result.get("intent", {})
            eq_type = (intent.get("equipment_type") or "").lower()
            if "controller" in eq_type or "joystick" in eq_type:
                from api.db import get_conn as _get_conn
                _conn = _get_conn()
                _avoip = {r[0] for r in _conn.execute("SELECT id FROM products WHERE category='av_over_ip'")}
                _conn.close()
                semantic_hits = [h for h in semantic_hits if h["id"] not in _avoip]
            sql_skus = [h["id"] for h in semantic_hits] if semantic_hits else []
            categories = []

        # NOTE: the LLM sanity filter is NOT run here. It used to run synchronously
        # in this POST, blocking the response for tens of seconds — and then ran a
        # SECOND time inside the SSE stream (stream_flow_a_recommendation), doubling
        # the wait. The frontend ignores `candidates` from this response anyway and
        # renders products exclusively from the SSE stream. So we return immediately
        # with the consultant message and let the stream do the (single) filter pass.
        initial_candidates = _fetch_products_by_skus(sql_skus)

        # Store stream context so SSE endpoint can pick it up
        _pending_recs[sid] = {
            "status": "context_ready",
            "flow": flow,
            "search_query": search_query,
            "sql_skus": sql_skus,
            "categories": categories,
            "scenario_answers": scenario_answers,
            "scenario_plan": scenario_plan,
            "session_dict": session_dict,
        }

        # Сбрасываем план сессии
        _scenario_state[sid] = {}
        save_chat_state(sid, {}, history)

        return ChatResponse(
            message=result["message"],
            chips=result.get("chips", []),
            ready_to_search=True,
            candidates=initial_candidates,
            recommendation=None,
            session=session,
        )

    return ChatResponse(
        message=result["message"],
        chips=result.get("chips", []),
        ready_to_search=False,
        required_roles=result.get("required_roles", []),
        session=session,
    )


# ─── Debug ────────────────────────────────────────────────────────────────────

@app.get("/debug/session/{session_id}", tags=["Debug"])
def debug_session(session_id: str):
    """Полное состояние сессии для отладки — история, план сценария, раунды."""
    session = get_session(session_id)
    db_scenario, db_history = load_chat_state(session_id)

    scenario = _scenario_state.get(session_id) or db_scenario or {}
    history  = _chat_histories.get(session_id) or db_history or []

    plan = scenario.get("_scenario_plan") or {}

    return {
        "session_id":          session_id,
        "session_found":       session is not None,
        "clarification_round": scenario.get("_clarification_round"),
        "selected_roles":      scenario.get("_selected_roles"),
        "scenario_type":       plan.get("scenario_type"),
        "scenario_summary":    plan.get("scenario_summary"),
        "required_roles":      [r.get("role") for r in plan.get("required_roles", [])],
        "questions_count":     len(plan.get("clarifying_questions", [])),
        "answers":             scenario.get("_scenario_answers") or {},
        "history_turns":       len(history),
        "history": [
            {"role": m["role"], "preview": m["content"][:120]}
            for m in history
        ],
    }


# ─── Debug annotations ────────────────────────────────────────────────────────

import sqlite3 as _sqlite3
import json as _json
from datetime import datetime as _dt

_DEBUG_DB = "debug_annotations.db"

def _init_debug_db():
    conn = _sqlite3.connect(_DEBUG_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS annotated_sessions (
            id          TEXT PRIMARY KEY,
            session_id  TEXT,
            saved_at    TEXT,
            session_comment TEXT,
            msg_comments    TEXT,
            history         TEXT,
            products_shown  TEXT
        )
    """)
    conn.commit()
    conn.close()

_init_debug_db()


class SaveCommentsBody(BaseModel):
    session_id: str
    session_comment: str = ""
    msg_comments: dict = {}
    history: list = []
    products_shown: list = []


@app.post("/debug/save-comments", tags=["Debug"])
def save_comments(body: SaveCommentsBody):
    import uuid
    ann_id = str(uuid.uuid4())
    conn = _sqlite3.connect(_DEBUG_DB)
    conn.execute(
        "INSERT OR REPLACE INTO annotated_sessions VALUES (?,?,?,?,?,?,?)",
        (
            ann_id,
            body.session_id,
            _dt.utcnow().isoformat(),
            body.session_comment,
            _json.dumps(body.msg_comments),
            _json.dumps(body.history),
            _json.dumps(body.products_shown),
        )
    )
    conn.commit()
    conn.close()
    return {"ok": True, "annotation_id": ann_id}


@app.get("/debug/annotations", tags=["Debug"])
def list_annotations():
    conn = _sqlite3.connect(_DEBUG_DB)
    rows = conn.execute(
        "SELECT id, session_id, saved_at, session_comment FROM annotated_sessions ORDER BY saved_at DESC"
    ).fetchall()
    conn.close()
    return [
        {"id": r[0], "session_id": r[1], "saved_at": r[2],
         "session_comment": r[3] or ""}
        for r in rows
    ]


@app.get("/debug/annotations/{ann_id}", tags=["Debug"])
def get_annotation(ann_id: str):
    conn = _sqlite3.connect(_DEBUG_DB)
    row = conn.execute(
        "SELECT * FROM annotated_sessions WHERE id=?", (ann_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Not found")
    return {
        "id": row[0], "session_id": row[1], "saved_at": row[2],
        "session_comment": row[3],
        "msg_comments": _json.loads(row[4] or "{}"),
        "history": _json.loads(row[5] or "[]"),
        "products_shown": _json.loads(row[6] or "[]"),
    }


@app.delete("/debug/annotations/{ann_id}", tags=["Debug"])
def delete_annotation(ann_id: str):
    conn = _sqlite3.connect(_DEBUG_DB)
    cur = conn.execute("DELETE FROM annotated_sessions WHERE id=?", (ann_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Not found")
    return {"ok": True}


# ─── Recommendation streaming (SSE) ──────────────────────────────────────────

@app.get("/chat/stream/{session_id}", tags=["Chat"])
def stream_recommendation_sse(session_id: str):
    """SSE stream: emits product cards one by one as LLM writes about them."""
    ctx = _pending_recs.get(session_id)
    if not ctx or ctx.get("status") != "context_ready":
        raise HTTPException(404, "No pending stream for this session")

    flow          = ctx["flow"]
    search_query  = ctx["search_query"]
    sql_skus      = ctx["sql_skus"]
    categories    = ctx["categories"]
    answers       = ctx["scenario_answers"]
    plan          = ctx["scenario_plan"]
    session_dict  = ctx["session_dict"]

    def generate():
        import json as _json
        from api.universal_engine import stream_flow_a_recommendation

        print(f"[SSE] session={session_id} flow={flow} sql_skus={sql_skus}")
        full_text = []

        if flow in ("product_selection", "hybrid"):
            gen = stream_flow_a_recommendation(
                question=search_query,
                candidate_skus=sql_skus,
                session=session_dict,
                requested_categories=categories,
                answers=answers,
                plan=plan,
            )
        else:
            # Flow B: non-streaming recommendation + SKU detection in answer
            import re as _re
            print(f"[SSE Flow B] running get_universal_recommendation, sql_skus={sql_skus}")
            eng = get_universal_recommendation(
                question=search_query,
                session=session_dict,
                candidate_skus=sql_skus,
            )
            answer = eng["answer"]
            print(f"[SSE Flow B] answer length={len(answer)}, selected_skus={eng.get('selected_skus')}")
            # Emit product cards for any BZB Gear SKU mentioned in the answer
            seen: set[str] = set()
            for m in _re.finditer(r'\b((?:BG|BZ)-[\w-]+)\b', answer, _re.IGNORECASE):
                sku = m.group(1).upper()
                if sku not in seen:
                    seen.add(sku)
                    conn = get_conn()
                    row = conn.execute(
                        "SELECT * FROM products WHERE id=? AND (site_category IS NULL OR site_category != 'Discontinued') AND (stock_status IS NULL OR stock_status NOT IN ('Discontinued', 'Limited Stock'))",
                        (sku,)
                    ).fetchone()
                    conn.close()
                    if row:
                        p = Product(**row_to_dict(row))
                        yield f"data: {_json.dumps({'type': 'product', 'product': p.model_dump()})}\n\n"
            yield f"data: {_json.dumps({'type': 'text', 'chunk': answer})}\n\n"
            yield f"data: {_json.dumps({'type': 'done'})}\n\n"
            return

        try:
            for ev in gen:
                event_type = ev[0]
                if event_type == "text":
                    data = ev[1]
                    full_text.append(data)
                    yield f"data: {_json.dumps({'type': 'text', 'chunk': data})}\n\n"

                elif event_type == "product":
                    sku = ev[1]
                    tier = ev[2] if len(ev) > 2 else "perfect"
                    print(f"[SSE Flow A] product event sku={sku} tier={tier}")
                    conn = get_conn()
                    row = conn.execute(
                        "SELECT * FROM products WHERE id=? AND (site_category IS NULL OR site_category != 'Discontinued') AND (stock_status IS NULL OR stock_status NOT IN ('Discontinued', 'Limited Stock'))",
                        (sku,)
                    ).fetchone()
                    conn.close()
                    if row:
                        p = Product(**row_to_dict(row))
                        yield f"data: {_json.dumps({'type': 'product', 'product': p.model_dump(), 'tier': tier})}\n\n"
                    else:
                        print(f"[SSE Flow A] sku {sku} not found in DB")

                elif event_type == "done":
                    yield f"data: {_json.dumps({'type': 'done'})}\n\n"
        except Exception as exc:
            import traceback
            print(f"[SSE ERROR] {exc}\n{traceback.format_exc()}")
            yield f"data: {_json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── Diagram ──────────────────────────────────────────────────────────────────

class DiagramRequest(BaseModel):
    recommendation: str


@app.post("/diagram", tags=["Chat"])
def generate_diagram_endpoint(body: DiagramRequest):
    """Extract node/connection structure from recommendation text for SVG rendering."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(400, "OPENAI_API_KEY not set")
    from api.diagram import extract_diagram
    return extract_diagram(body.recommendation)


# ─── DB stats ─────────────────────────────────────────────────────────────────

@app.get("/stats", tags=["Info"])
def stats():
    """Database statistics."""
    conn = get_conn()
    cats = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM products GROUP BY category ORDER BY cnt DESC"
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    with_specs = conn.execute(
        "SELECT COUNT(*) FROM products WHERE inputs IS NOT NULL AND outputs IS NOT NULL"
    ).fetchone()[0]
    conn.close()

    from api.db import get_chroma
    chroma = get_chroma()
    chunk_count = chroma.count() if chroma else 0

    return {
        "total_products": total,
        "products_with_io_specs": with_specs,
        "manual_chunks_indexed": chunk_count,
        "categories": {row[0]: row[1] for row in cats},
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
