"""Sub requests hygiene; keyholder approves; timed unlock/relock with late punish."""

from __future__ import annotations

import json
import logging
import re
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


def reset_hygiene() -> dict[str, Any]:
    """Force idle so the lockee can request again after a deny or stuck state."""
    return _set("idle", **{k: v for k, v in _IDLE.items() if k != "status"})


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
    return _set(
        "denied",
        requested_at="",
        approved_at="",
        unlocked_at="",
        deadline_at="",
        punished=False,
        last_error="",
    )


def mark_unlocked(*, allowed_seconds: int) -> dict[str, Any]:
    with _lock:
        state = _load_raw()
        if state["status"] != "approved":
            raise ValueError("Hygiene is not approved yet")
        allowed = max(60, int(state.get("allowed_seconds") or allowed_seconds or 600))
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
    return reset_hygiene()


def mark_error(message: str) -> dict[str, Any]:
    with _lock:
        state = _load_raw()
        state["last_error"] = (message or "")[:240]
        _save_raw(state)
        return _public(state)


def should_punish() -> bool:
    view = snapshot()
    return bool(view["status"] == "unlocked" and view["late"] and not view["punished"])


_KH_DURATION = re.compile(
    r"^\s*(?:ok(?:ay)?|yes|approve[d]?|sure)?\s*"
    r"(\d+(?:\.\d+)?)\s*"
    r"(m|mins?|minutes?|h|hrs?|hours?)?\s*[.!]?\s*$",
    re.I,
)
_KH_DENY = re.compile(
    r"^\s*(no|nope|deny|denied|reject(?:ed)?|not now)\s*[.!]?\s*$",
    re.I,
)
_KH_APPROVE_BARE = re.compile(
    r"^\s*(yes|ok|okay|approve[d]?|sure|go ahead)\s*[.!]?\s*$",
    re.I,
)


def parse_kh_hygiene_reply(
    message: str, *, default_seconds: int = 600
) -> tuple[str, int] | None:
    """Keyholder answering a pending request: ('approve', secs) or ('deny', 0)."""
    text = (message or "").strip()
    if not text:
        return None
    if _KH_DENY.fullmatch(text):
        return ("deny", 0)
    dur = _KH_DURATION.fullmatch(text)
    if dur:
        n = float(dur.group(1))
        if n <= 0 or n > 24 * 60:
            return None
        unit = (dur.group(2) or "m").lower()
        secs = int(n * 3600) if unit.startswith("h") else int(n * 60)
        return ("approve", max(60, secs))
    if _KH_APPROVE_BARE.fullmatch(text):
        return ("approve", max(60, int(default_seconds or 600)))
    return None


def format_hygiene_director(view: dict[str, Any] | None = None) -> str:
    """Tell the model hygiene is buttons-only — never LOCK tags."""
    st = view if isinstance(view, dict) else snapshot()
    status = str(st.get("status") or "idle")
    mins = max(1, int(st.get("allowed_seconds") or 600) // 60)
    remain = st.get("remaining_seconds")
    late = bool(st.get("late"))
    lines = [
        "[HYGIENE FLOW — buttons only, never [[[LOCK]]] tags, never pillory, "
        "never Chaster temporary-opening]",
    ]
    if status == "requested":
        lines.append(
            "Lockee requested hygiene. If she types a duration (e.g. 15 mins), "
            "that Approves the unlock window — do NOT change Chaster lock time, "
            "freeze, or hide the timer. Point him at Unlock next to Group. "
            "Her Unlock/Lock buttons are for teasing him out of the cage, not this timer."
        )
    elif status == "approved":
        lines.append(
            f"Approved for {mins} min after he unlocks. "
            "Tell the lockee to tap Unlock, then Lock in this chat. Timer starts on Unlock."
        )
    elif status == "unlocked":
        if late:
            lines.append("He is LATE relocking. Tell him to tap Lock now. Punishment may apply.")
        else:
            left = f"{max(0, int(remain or 0)) // 60}m" if remain is not None else f"{mins}m"
            lines.append(
                f"Box is open. He must tap Lock within {left}. Do not invent a Chaster unlock."
            )
    elif status == "denied":
        lines.append("Last request was denied. He may tap Hygiene to request again.")
    else:
        lines.append(
            "Idle. Lockee taps Hygiene next to Group. Keyholder then sets a timescale."
        )
    return "\n".join(lines)


def mark_punished() -> dict[str, Any]:
    with _lock:
        state = _load_raw()
        state["punished"] = True
        _save_raw(state)
        return _public(state)
