"""SQLite + ChromaDB connection helpers."""
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "products.db"
CHROMA_PATH = str(Path(__file__).parent.parent / "chroma_db")

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for field in ("input_signals", "output_signals", "resolutions"):
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                d[field] = []
        else:
            d[field] = []
    return d

def init_chat_state_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_state (
            session_id TEXT PRIMARY KEY,
            scenario_json TEXT,
            history_json TEXT,
            updated_at REAL DEFAULT (unixepoch('now'))
        )
    """)
    conn.execute("""CREATE TABLE IF NOT EXISTS chat_results (
        session_id TEXT PRIMARY KEY,
        results_json TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS chat_session_fields (
        session_id TEXT PRIMARY KEY,
        fields_json TEXT NOT NULL
    )""")
    conn.commit()
    conn.close()

def save_chat_state(session_id: str, scenario: dict, history: list):
    conn = get_conn()
    conn.execute("""
        INSERT INTO chat_state (session_id, scenario_json, history_json, updated_at)
        VALUES (?, ?, ?, unixepoch('now'))
        ON CONFLICT(session_id) DO UPDATE SET
            scenario_json = excluded.scenario_json,
            history_json  = excluded.history_json,
            updated_at    = excluded.updated_at
    """, (session_id, json.dumps(scenario), json.dumps(history)))
    conn.commit()
    conn.close()

def load_chat_state(session_id: str) -> tuple[dict, list]:
    conn = get_conn()
    row = conn.execute(
        "SELECT scenario_json, history_json FROM chat_state WHERE session_id=?", (session_id,)
    ).fetchone()
    conn.close()
    if not row:
        return {}, []
    return (
        json.loads(row["scenario_json"] or "{}"),
        json.loads(row["history_json"] or "[]"),
    )


def save_chat_result(session_id: str, result: dict) -> None:
    conn = get_conn()
    row = conn.execute("SELECT results_json FROM chat_results WHERE session_id=?", (session_id,)).fetchone()
    results = json.loads(row[0]) if row else []
    # A browser refresh can reconnect to the same pending SSE search. Keep one
    # result block per conversational position, replacing a partial prior run.
    if results and results[-1].get("history_index") == result.get("history_index"):
        results[-1] = result
    else:
        results.append(result)
    conn.execute("""INSERT INTO chat_results (session_id, results_json) VALUES (?, ?)
        ON CONFLICT(session_id) DO UPDATE SET results_json=excluded.results_json""",
        (session_id, json.dumps(results)))
    conn.commit()
    conn.close()


def load_chat_results(session_id: str) -> list[dict]:
    conn = get_conn()
    row = conn.execute("SELECT results_json FROM chat_results WHERE session_id=?", (session_id,)).fetchone()
    conn.close()
    return json.loads(row[0]) if row else []


def save_session_fields(session_id: str, fields: dict) -> None:
    conn = get_conn()
    conn.execute("""INSERT INTO chat_session_fields (session_id, fields_json) VALUES (?, ?)
        ON CONFLICT(session_id) DO UPDATE SET fields_json=excluded.fields_json""",
        (session_id, json.dumps(fields)))
    conn.commit()
    conn.close()


def load_session_fields(session_id: str) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT fields_json FROM chat_session_fields WHERE session_id=?", (session_id,)).fetchone()
    conn.close()
    return json.loads(row[0]) if row else {}

def get_chroma():
    """Return ChromaDB collection (None if not yet ingested)."""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        return client.get_or_create_collection(
            name="manual_chunks",
            metadata={"hnsw:space": "cosine"},
        )
    except Exception:
        return None
