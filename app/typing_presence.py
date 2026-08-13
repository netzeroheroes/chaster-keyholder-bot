"""Ephemeral per-room typing indicators for group/private chat."""

from __future__ import annotations

import time
from threading import Lock

# How long a typing heartbeat stays visible without refresh.
TTL_SECONDS = 4.0

_lock = Lock()
# room -> speaker_key -> {label, ts}
_store: dict[str, dict[str, dict[str, float | str]]] = {}


def set_typing(room: str, speaker: str, label: str = "") -> None:
    r = (room or "").strip() or "group"
    sp = (speaker or "").strip()
    if not sp:
        return
    now = time.monotonic()
    with _lock:
        bucket = _store.setdefault(r, {})
        bucket[sp] = {
            "label": (label or sp).strip()[:40],
            "ts": now,
        }


def clear_typing(room: str, speaker: str) -> None:
    r = (room or "").strip() or "group"
    sp = (speaker or "").strip()
    if not sp:
        return
    with _lock:
        bucket = _store.get(r)
        if not bucket:
            return
        bucket.pop(sp, None)
        if not bucket:
            _store.pop(r, None)


def list_typing(room: str, *, exclude: str = "") -> list[dict[str, str]]:
    r = (room or "").strip() or "group"
    now = time.monotonic()
    ex = (exclude or "").strip()
    out: list[dict[str, str]] = []
    with _lock:
        bucket = _store.get(r) or {}
        dead = [k for k, v in bucket.items() if now - float(v["ts"]) > TTL_SECONDS]
        for k in dead:
            bucket.pop(k, None)
        if not bucket and r in _store:
            _store.pop(r, None)
            return []
        for key, v in bucket.items():
            if ex and key == ex:
                continue
            out.append({"speaker": key, "label": str(v.get("label") or key)})
    out.sort(key=lambda x: x["label"].lower())
    return out
