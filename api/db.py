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
