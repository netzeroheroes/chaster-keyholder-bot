"""Sub requests hygiene; keyholder approves; timed unlock/relock with late punish."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PATH = DATA_DIR / "hygiene_request.json"

_lock = Lock()

_IDLE = {
    "status": "idle",
    "requested_at": "",
    "approved_at": "",
    "unlocked_at": "",
    "deadline_at": "",
    "allowed_seconds": 600,
    "punished": False,
    "last_error": "",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str:
    if not dt:
        return ""
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse(iso: str) -> datetime | None:
    raw = (iso or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_raw() -> dict[str, Any]:
    if not PATH.is_file():
        return dict(_IDLE)
    try:
        raw = json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_IDLE)
    if not isinstance(raw, dict):
        return dict(_IDLE)
    out = dict(_IDLE)
    out.update({k: raw.get(k, out[k]) for k in out})
    return out


def _save_raw(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def snapshot() -> dict[str, Any]:
    with _lock:
        state = _load_raw()
    return _public(state)


def _public(state: dict[str, Any]) -> dict[str, Any]:
    status = str(state.get("status") or "idle")
    deadline = _parse(str(state.get("deadline_at") or ""))
    remaining = None
    late = False
    if status == "unlocked" and deadline:
        remaining = int((deadline - _now()).total_seconds())
        late = remaining <= 0
        remaining = max(0, remaining)
    return {
        "status": status,
        "requested_at": state.get("requested_at") or "",
        "approved_at": state.get("approved_at") or "",
        "unlocked_at": state.get("unlocked_at") or "",
        "deadline_at": state.get("deadline_at") or "",
        "allowed_seconds": int(state.get("allowed_seconds") or 600),
        "punished": bool(state.get("punished")),
        "last_error": state.get("last_error") or "",
        "remaining_seconds": remaining,
        "late": late,
    }


def _set(status: str, **extra: Any) -> dict[str, Any]:
    with _lock:
        state = _load_raw()
        state["status"] = status
        state.update(extra)
        _save_raw(state)
        return _public(state)


def request_hygiene(*, allowed_seconds: int) -> dict[str, Any]:
    with _lock:
        state = _load_raw()
        if state["status"] in {"requested", "approved", "unlocked"}:
            return _public(state)
        state = dict(_IDLE)
        state["status"] = "requested"
        state["requested_at"] = _iso(_now())
        state["allowed_seconds"] = max(60, int(allowed_seconds or 600))
        _save_raw(state)
        return _public(state)


def approve_hygiene(*, allowed_seconds: int) -> dict[str, Any]:
    with _lock:
        state = _load_raw()
        if state["status"] not in {"requested", "approved"}:
            raise ValueError("No hygiene request to approve")
        state["status"] = "approved"
        state["approved_at"] = _iso(_now())
        state["allowed_seconds"] = max(60, int(allowed_seconds or state.get("allowed_seconds") or 600))
        state["punished"] = False
        state["last_error"] = ""
        _save_raw(state)
        return _public(state)


def deny_hygiene() -> dict[str, Any]:
    return _set("idle", **{k: v for k, v in _IDLE.items() if k != "status"})


def mark_unlocked(*, allowed_seconds: int) -> dict[str, Any]:
    with _lock:
        state = _load_raw()
        if state["status"] != "approved":
            raise ValueError("Hygiene is not approved yet")
        allowed = max(60, int(allowed_seconds or state.get("allowed_seconds") or 600))
        start = _now()
        state["status"] = "unlocked"
        state["unlocked_at"] = _iso(start)
        state["allowed_seconds"] = allowed
        state["deadline_at"] = _iso(start + timedelta(seconds=allowed))
        state["punished"] = False
        state["last_error"] = ""
        _save_raw(state)
        return _public(state)


def mark_relocked() -> dict[str, Any]:
    return deny_hygiene()


def mark_error(message: str) -> dict[str, Any]:
    with _lock:
        state = _load_raw()
        state["last_error"] = (message or "")[:240]
        _save_raw(state)
        return _public(state)


def should_punish() -> bool:
    view = snapshot()
    return bool(view["status"] == "unlocked" and view["late"] and not view["punished"])


def mark_punished() -> dict[str, Any]:
    with _lock:
        state = _load_raw()
        state["punished"] = True
        _save_raw(state)
        return _public(state)
