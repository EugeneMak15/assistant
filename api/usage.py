"""Per-chat OpenAI token usage and estimated USD cost."""

import logging
from contextlib import contextmanager
from contextvars import ContextVar

from .db import get_conn


_session_id: ContextVar[str | None] = ContextVar("usage_session_id", default=None)

# USD per million tokens, Standard processing, checked 2026-09-29.
# https://developers.openai.com/api/docs/models/
# Keep these rates explicit: the UI shows an estimate, not an OpenAI invoice.
_RATES = {
    "gpt-5.6-sol": (4.00, 0.40, 20.00, 5.00),
    "gpt-5.5": (5.00, 0.50, 30.00, 5.00),
    "gpt-4o-mini": (0.15, 0.075, 0.60, 0.15),
    "o4-mini": (1.10, 0.275, 4.40, 1.10),
    "text-embedding-3-small": (0.02, 0.02, 0.00, 0.02),
}


def init_usage_table() -> None:
    conn = get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_usage (
                id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL,
                cached_tokens INTEGER NOT NULL,
                cache_write_tokens INTEGER NOT NULL,
                completion_tokens INTEGER NOT NULL,
                estimated_cost_usd REAL,
                created_at REAL DEFAULT (unixepoch('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS chat_usage_session_idx ON chat_usage(session_id)")
        conn.commit()
    finally:
        conn.close()


@contextmanager
def track_session(session_id: str | None):
    token = _session_id.set(session_id)
    try:
        yield
    finally:
        _session_id.reset(token)


def _field(obj, name: str, default=0):
    if obj is None:
        return default
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def estimate_cost(model: str, prompt: int, cached: int, cache_write: int, output: int) -> float | None:
    rates = next((rates for name, rates in _RATES.items()
                  if model == name or model.startswith(name + "-")), None)
    if rates is None:
        return None
    input_rate, cached_rate, output_rate, write_rate = rates
    uncached = max(prompt - cached - cache_write, 0)
    return (uncached * input_rate + cached * cached_rate
            + cache_write * write_rate + output * output_rate) / 1_000_000


def record_usage(response) -> None:
    """Record a completed API response; missing usage must not break the chat."""
    sid = _session_id.get()
    usage = _field(response, "usage", None)
    if not sid or usage is None:
        return
    model = str(_field(response, "model", "unknown") or "unknown")
    prompt = int(_field(usage, "prompt_tokens", _field(usage, "input_tokens", 0)) or 0)
    output = int(_field(usage, "completion_tokens", _field(usage, "output_tokens", 0)) or 0)
    details = _field(usage, "prompt_tokens_details", _field(usage, "input_tokens_details", None))
    cached = min(prompt, int(_field(details, "cached_tokens", 0) or 0))
    cache_write = min(prompt - cached, int(_field(details, "cache_write_tokens", 0) or 0))
    cost = estimate_cost(model, prompt, cached, cache_write, output)
    try:
        conn = get_conn()
        try:
            conn.execute("""
                INSERT INTO chat_usage
                    (session_id, model, prompt_tokens, cached_tokens, cache_write_tokens,
                     completion_tokens, estimated_cost_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (sid, model, prompt, cached, cache_write, output, cost))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logging.getLogger(__name__).exception("Could not record OpenAI usage for session %s", sid)


def get_session_usage(session_id: str) -> dict:
    conn = get_conn()
    try:
        row = conn.execute("""
            SELECT COUNT(*) AS requests,
                   COALESCE(SUM(prompt_tokens), 0) AS input_tokens,
                   COALESCE(SUM(completion_tokens), 0) AS output_tokens,
                   COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd,
                   COALESCE(SUM(CASE WHEN estimated_cost_usd IS NULL THEN 1 ELSE 0 END), 0)
                       AS unpriced_requests
            FROM chat_usage WHERE session_id = ?
        """, (session_id,)).fetchone()
    finally:
        conn.close()
    return {
        "session_id": session_id,
        "requests": row["requests"],
        "input_tokens": row["input_tokens"],
        "output_tokens": row["output_tokens"],
        "estimated_cost_usd": round(row["estimated_cost_usd"], 8),
        "unpriced_requests": row["unpriced_requests"],
    }
