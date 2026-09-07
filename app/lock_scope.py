"""Per-lock scope so session ids and files never collide across locks."""

from __future__ import annotations

import re
from contextvars import ContextVar, Token

_SCOPE: ContextVar[str] = ContextVar("lock_scope", default="")
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def normalize_lock_id(raw: str | None) -> str:
    text = _SAFE.sub("", str(raw or "").strip())
    return text[:80]


def lock_scope_id(*, lock_id: str = "", session_id: str = "") -> str:
    """Stable per-lock key. Prefer Chaster lock id; fall back to partner sessionId."""
    lid = normalize_lock_id(lock_id)
    if lid:
        return lid
    sid = normalize_lock_id(session_id)
    if sid and sid != "dev":
        return f"sid-{sid}"
    return ""


def current_lock_scope() -> str:
    return _SCOPE.get() or ""


def set_lock_scope(scope: str) -> Token[str]:
    return _SCOPE.set(normalize_lock_id(scope) if scope else "")


def reset_lock_scope(token: Token[str]) -> None:
    _SCOPE.reset(token)


def bind_lock_scope(*, lock_id: str = "", session_id: str = "") -> Token[str]:
    return set_lock_scope(lock_scope_id(lock_id=lock_id, session_id=session_id))


def display_key(room: str, scope: str | None = None) -> str:
    room_key = (room or "").strip() or "group"
    # Already scoped (re-entrant)
    if room_key.startswith("lock:"):
        return room_key
    lid = normalize_lock_id(scope) if scope is not None else current_lock_scope()
    if lid:
        return f"lock:{lid}:{room_key}"
    return room_key


def public_room(key: str) -> str:
    raw = (key or "").strip() or "group"
    if raw.startswith("lock:"):
        parts = raw.split(":", 2)
        if len(parts) == 3:
            return parts[2] or "group"
    return raw


def session_id_for(room: str, lock_id: str | None = None) -> str:
    room_key = (room or "").strip() or "group"
    lid = normalize_lock_id(lock_id) if lock_id is not None else current_lock_scope()
    if lid:
        return f"lock:{lid}:room:{room_key}"
    return f"room:{room_key}"
