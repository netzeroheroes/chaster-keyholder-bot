"""Track recent bot-initiated Chaster mutations for lock-history attribution.

Chaster logs keyholder-token API edits (e.g. share-link config) as
role=keyholder — same as a manual Mistress click. Without this ledger,
lock-watch mislabels those as "manual keyholder action — not the bot".
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Any

# How long a bot edit may be matched to a history event.
TTL_SECONDS = 180.0

_lock = Lock()
# newest last: {slug, action, ts}
_notes: list[dict[str, Any]] = []

# History type → expected note action (empty = any)
_TYPE_ACTIONS: dict[str, str] = {
    "extension_updated": "updated",
    "extension_enabled": "enabled",
    "extension_disabled": "disabled",
}


def note_bot_extension_change(slug: str, *, action: str = "updated") -> None:
    s = (slug or "").strip().lower()
    if not s:
        return
    a = (action or "updated").strip().lower()
    if a not in ("updated", "enabled", "disabled"):
        a = "updated"
    now = time.monotonic()
    with _lock:
        _prune(now)
        _notes.append({"slug": s, "action": a, "ts": now})
        # Cap memory
        if len(_notes) > 40:
            del _notes[:-40]


def note_bot_extension_changes(
    slugs: list[str] | tuple[str, ...] | set[str],
    *,
    action: str = "updated",
) -> None:
    for slug in slugs:
        note_bot_extension_change(slug, action=action)


def _prune(now: float | None = None) -> None:
    t = time.monotonic() if now is None else now
    keep = [n for n in _notes if t - float(n["ts"]) <= TTL_SECONDS]
    _notes.clear()
    _notes.extend(keep)


def _event_slug(event: dict[str, Any]) -> str:
    ext = str(event.get("extension") or "").strip().lower()
    if ext:
        return ext
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    return str(payload.get("slug") or "").strip().lower()


def is_bot_extension_history_event(event: dict[str, Any]) -> bool:
    """True if this history row matches a recent bot-driven extension edit."""
    etype = str(event.get("type") or "")
    if etype not in _TYPE_ACTIONS:
        return False
    slug = _event_slug(event)
    if not slug:
        return False
    want = _TYPE_ACTIONS[etype]
    now = time.monotonic()
    with _lock:
        _prune(now)
        for n in reversed(_notes):
            if str(n.get("slug") or "") != slug:
                continue
            # Allow updated notes to match enabled/disabled if timing is tight
            # (park/swap), but prefer exact action.
            action = str(n.get("action") or "")
            if action == want or (want == "updated" and action == "updated"):
                return True
            if action in ("enabled", "disabled", "updated") and want in (
                "enabled",
                "disabled",
                "updated",
            ):
                # Same slug rewritten during ensure/park — still ours.
                return True
    return False
