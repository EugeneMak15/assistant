"""Read-only reporting queries for administrator chat audits."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .db import get_conn


PACIFIC = ZoneInfo("America/Los_Angeles")


def _epoch(day: str, end: bool = False) -> float:
    parsed = date.fromisoformat(day)
    if end:
        parsed += timedelta(days=1)
    return datetime.combine(parsed, time.min, PACIFIC).timestamp()


def get_chat_report(from_date: str, to_date: str, ip: str, page: int, page_size: int) -> dict:
    start = _epoch(from_date)
    end = _epoch(to_date, end=True)
    ip = ip.strip()
    where = "COALESCE(v.created_at,s.updated_at)>=? AND COALESCE(v.created_at,s.updated_at)<?"
    params: list[object] = [start, end]
    if ip:
        where += " AND COALESCE(v.ip_address,'') LIKE ?"
        params.append(f"%{ip}%")

    usage = """
        SELECT session_id, COUNT(*) api_calls,
               COALESCE(SUM(prompt_tokens),0) prompt_tokens,
               COALESCE(SUM(cached_tokens),0) cached_tokens,
               COALESCE(SUM(completion_tokens),0) completion_tokens,
               COALESCE(SUM(estimated_cost_usd),0) cost
        FROM chat_usage GROUP BY session_id
    """
    base = f"""
        FROM chat_state s
        LEFT JOIN chat_visitors v ON v.session_id=s.session_id
        LEFT JOIN ({usage}) u ON u.session_id=s.session_id
        LEFT JOIN chat_results r ON r.session_id=s.session_id
        WHERE {where}
    """

    conn = get_conn()
    try:
        totals = conn.execute(
            "SELECT COUNT(*) sessions, COALESCE(SUM(u.cost),0) cost, "
            "COALESCE(SUM(u.prompt_tokens),0) prompt_tokens, "
            "COALESCE(SUM(u.cached_tokens),0) cached_tokens, "
            "COALESCE(SUM(u.completion_tokens),0) completion_tokens, "
            "COALESCE(SUM(u.api_calls),0) api_calls " + base,
            params,
        ).fetchone()
        offset = (page - 1) * page_size
        rows = conn.execute(
            "SELECT s.session_id,s.history_json,s.updated_at,v.created_at,v.ip_address,v.visitor_id,"
            "COALESCE(u.api_calls,0) api_calls,COALESCE(u.prompt_tokens,0) prompt_tokens,"
            "COALESCE(u.cached_tokens,0) cached_tokens,COALESCE(u.completion_tokens,0) completion_tokens,"
            "COALESCE(u.cost,0) cost,COALESCE(r.results_json,'[]') results_json "
            + base + " ORDER BY COALESCE(v.created_at,s.updated_at) DESC LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()
    finally:
        conn.close()

    sessions = []
    total_messages = 0
    for row in rows:
        try:
            history = json.loads(row["history_json"] or "[]")
        except json.JSONDecodeError:
            history = []
        try:
            results = json.loads(row["results_json"] or "[]")
        except json.JSONDecodeError:
            results = []
        total_messages += len(history)
        started = row["created_at"] or row["updated_at"]
        sessions.append({
            "session_id": row["session_id"],
            "ip": row["ip_address"] or "unknown",
            "visitor_id": row["visitor_id"],
            "started_at": datetime.fromtimestamp(started, PACIFIC).isoformat(),
            "updated_at": datetime.fromtimestamp(row["updated_at"], PACIFIC).isoformat(),
            "duration_seconds": max(0, int(row["updated_at"] - started)),
            "messages": history,
            "message_count": len(history),
            "results": results,
            "usage": {
                "api_calls": row["api_calls"],
                "prompt_tokens": row["prompt_tokens"],
                "cached_tokens": row["cached_tokens"],
                "completion_tokens": row["completion_tokens"],
                "cost_usd": row["cost"],
            },
        })

    count = int(totals["sessions"])
    return {
        "timezone": "America/Los_Angeles",
        "filters": {"from": from_date, "to": to_date, "ip": ip},
        "summary": {
            "sessions": count,
            "messages_on_page": total_messages,
            "api_calls": int(totals["api_calls"]),
            "prompt_tokens": int(totals["prompt_tokens"]),
            "cached_tokens": int(totals["cached_tokens"]),
            "completion_tokens": int(totals["completion_tokens"]),
            "cost_usd": float(totals["cost"]),
            "average_cost_usd": float(totals["cost"]) / count if count else 0,
        },
        "pagination": {
            "page": page, "page_size": page_size,
            "pages": max(1, math.ceil(count / page_size)),
        },
        "sessions": sessions,
    }
