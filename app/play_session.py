"""Time a play Unlock→Lock and add agreed minutes-per-minute to Chaster."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PATH = DATA_DIR / "play_session.json"

DEFAULT_RATE = 2.0
MIN_OUT_SECONDS = 30
MAX_RATE = 10.0

_lock = Lock()

_IDLE = {
    "status": "idle",
    "rate": 0.0,
    "unlocked_at": "",
    "last_out_seconds": 0,
    "last_added_seconds": 0,
    "last_error": "",
}

_RATE_EXPLICIT = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*"
    r"(?:"
    r"x\b|"
    r":\s*1\b|"
    r"minutes?\s+(?:locked\s+)?per\s+(?:each\s+)?minute|"
    r"min(?:ute)?s?\s+(?:locked\s+)?per\s+min(?:ute)?s?"
    r")",
    re.I,
)
_DOUBLE_PRICE = re.compile(
    r"\bdouble(?:\s+time|\s+price|\s+the\s+price)\b",
    re.I,
)
_YES_PRICE = re.compile(
    r"\b("
    r"yes[,.]?\s+(?:2x|add(?:\s+the)?\s+time|time\s+(?:it|the\s+session)|do\s+it)|"
    r"time\s+(?:the\s+session|unlock\s+to\s+lock)|"
    r"use\s+(?:the\s+)?(?:play\s+)?(?:timer|multiplier|price)|"
    r"agreed(?:\s+to)?(?:\s+the)?(?:\s+price|\s+2x|\s+timer)?"
    r")\b",
    re.I,
)
_NO_PRICE = re.compile(
    r"\b("
    r"no\s+(?:price|extra\s+time|added\s+time|multiplier)|"
    r"free\s+(?:hour|session)|"
    r"don'?t\s+add(?:\s+time)?"
    r")\b",
    re.I,
)


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
    try:
        out["rate"] = float(out.get("rate") or 0)
    except (TypeError, ValueError):
        out["rate"] = 0.0
    for key in ("last_out_seconds", "last_added_seconds"):
        try:
            out[key] = int(out.get(key) or 0)
        except (TypeError, ValueError):
            out[key] = 0
    return out


def _save_raw(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _clamp_rate(rate: float) -> float:
    n = float(rate)
    if n <= 0:
        return 0.0
    return min(MAX_RATE, max(1.0, n))


def _elapsed(state: dict[str, Any]) -> int:
    start = _parse(str(state.get("unlocked_at") or ""))
    if not start:
        return 0
    return max(0, int((_now() - start).total_seconds()))


def _public(state: dict[str, Any]) -> dict[str, Any]:
    status = str(state.get("status") or "idle")
    rate = float(state.get("rate") or 0)
    elapsed = _elapsed(state) if status == "running" else 0
    pending = int(round(elapsed * rate)) if rate > 0 and elapsed else 0
    return {
        "status": status,
        "rate": rate,
        "unlocked_at": state.get("unlocked_at") or "",
        "elapsed_seconds": elapsed,
        "pending_add_seconds": pending,
        "last_out_seconds": int(state.get("last_out_seconds") or 0),
        "last_added_seconds": int(state.get("last_added_seconds") or 0),
        "last_error": state.get("last_error") or "",
    }


def snapshot() -> dict[str, Any]:
    with _lock:
        return _public(_load_raw())


def parse_play_rate(message: str) -> float | None:
    """Return a minutes-per-minute rate, 0 to cancel, or None if unsaid."""
    text = (message or "").strip()
    if not text:
        return None
    if _NO_PRICE.search(text):
        return 0.0
    hit = _RATE_EXPLICIT.search(text)
    if hit:
        try:
            n = float(hit.group(1))
        except (TypeError, ValueError):
            return None
        if n <= 0 or n > MAX_RATE:
            return None
        return _clamp_rate(n)
    if _DOUBLE_PRICE.search(text):
        return DEFAULT_RATE
    if _YES_PRICE.search(text):
        return DEFAULT_RATE
    return None


def set_rate(rate: float) -> dict[str, Any]:
    with _lock:
        state = _load_raw()
        state["rate"] = _clamp_rate(rate)
        if state["rate"] <= 0:
            state["last_error"] = ""
        _save_raw(state)
        return _public(state)


def start_on_unlock() -> dict[str, Any]:
    """Start timing this Unlock. Keeps an already-running timer."""
    with _lock:
        state = _load_raw()
        if state.get("status") == "running" and state.get("unlocked_at"):
            return _public(state)
        state["status"] = "running"
        state["unlocked_at"] = _iso(_now())
        state["last_error"] = ""
        _save_raw(state)
        return _public(state)


def settle_on_lock() -> dict[str, Any] | None:
    """Stop the timer. Returns settlement, or None if nothing was running."""
    with _lock:
        state = _load_raw()
        if state.get("status") != "running" or not state.get("unlocked_at"):
            return None
        out = _elapsed(state)
        rate = float(state.get("rate") or 0)
        add = 0
        if rate > 0 and out >= MIN_OUT_SECONDS:
            add = max(60, int(round(out * rate)))
        state["status"] = "idle"
        state["unlocked_at"] = ""
        state["last_out_seconds"] = out
        state["last_added_seconds"] = add
        state["last_error"] = ""
        _save_raw(state)
        view = _public(state)
        view["out_seconds"] = out
        view["add_seconds"] = add
        return view


def mark_error(message: str) -> dict[str, Any]:
    with _lock:
        state = _load_raw()
        state["last_error"] = (message or "")[:240]
        _save_raw(state)
        return _public(state)


def format_play_session_block(view: dict[str, Any] | None = None) -> str:
    """Tell the model: no 1:1, wait for her yes, timer applies the add."""
    st = view if isinstance(view, dict) else snapshot()
    rate = float(st.get("rate") or 0)
    status = str(st.get("status") or "idle")
    lines = [
        "[PLAY SESSION TIMER — do not invent 1 minute added per minute out. "
        "That is not a price. Do not emit [[[LOCK]]] tags for this.]",
    ]
    if rate > 0:
        lines.append(
            f"She agreed: {rate:g} min locked per min he is out. "
            "Your Unlock starts the timer. Lock applies it."
        )
    else:
        lines.append(
            "No price agreed. If she wants one, offer 2 min locked per min out "
            "(or the rate she names). Wait for her yes. Do not add time yourself."
        )
    if status == "running":
        elapsed = int(st.get("elapsed_seconds") or 0)
        lines.append(
            f"He is OUT. Timer running (~{max(0, elapsed) // 60}m). "
            "Do not invent the add — Lock will apply it."
        )
    last_add = int(st.get("last_added_seconds") or 0)
    last_out = int(st.get("last_out_seconds") or 0)
    if status == "idle" and last_out and last_add:
        lines.append(
            f"Last session: {last_out // 60}m out → {last_add // 60}m added."
        )
    return "\n".join(lines)
