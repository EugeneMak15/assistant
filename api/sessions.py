"""In-memory session store (replace with Redis/Supabase for production)."""
import uuid
from .models import SessionState

_store: dict[str, SessionState] = {}


def create_session() -> SessionState:
    sid = str(uuid.uuid4())
    s = SessionState(session_id=sid)
    _store[sid] = s
    return s


def get_session(session_id: str) -> SessionState | None:
    return _store.get(session_id)


def restore_session(session_id: str, fields: dict | None = None) -> SessionState:
    """Recreate a session object under an existing id (e.g. after a server restart).

    Used so an in-progress conversation survives an in-memory store wipe — the
    persisted chat history is keyed by this id, so keeping the id intact lets the
    conversation continue instead of starting over.
    """
    data = {"session_id": session_id}
    if fields:
        data.update({k: v for k, v in fields.items() if v is not None})
    s = SessionState(**data)
    _store[session_id] = s
    return s


def update_session(session_id: str, updates: dict) -> SessionState | None:
    s = _store.get(session_id)
    if not s:
        return None
    data = s.model_dump()
    for k, v in updates.items():
        if v is not None:
            data[k] = v
    data["step"] = data.get("step", 0) + 1
    updated = SessionState(**data)
    _store[session_id] = updated
    return updated


def all_sessions() -> list[SessionState]:
    return list(_store.values())
