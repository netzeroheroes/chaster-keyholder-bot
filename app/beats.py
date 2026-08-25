"""Split one model turn into sequential chat bubbles — like a person texting."""

from __future__ import annotations

import re

_MSG_BLOCK = re.compile(
    r"\[\[\[(?:MSG|BEAT)\]\]\](.*?)\[\[\[/(?:MSG|BEAT)\]\]\]",
    re.DOTALL | re.IGNORECASE,
)
_MSG_TAG = re.compile(r"\[\[\[/?(?:MSG|BEAT)\]\]\]", re.IGNORECASE)
_KEEP_WHOLE = re.compile(r"\[\[\[(?:LOCK|GROUP|IMAGE)\]\]\]", re.IGNORECASE)
_ADDRESSED = re.compile(r"^.{0,48}(?:—|–| - )\s")


def multi_reply_director(*, room: str, lead_now: bool = False) -> str:
    if lead_now and (room or "") == "group":
        return (
            "[DIRECTOR: TWO TEXTS THIS TURN, like a person texting. "
            "[[[MSG]]] half-sentence ack to her [[[/MSG]]] then "
            "[[[MSG]]] first concrete order TO him [[[/MSG]]]. "
            "Do not glue them into one speech. Do not ask where to begin.]"
        )
    if (room or "") == "group":
        return (
            "[DIRECTOR: Text like a person. One short message is normal. "
            "If you need a pause, or to speak to both of them, emit 2–3 "
            "[[[MSG]]]…[[[/MSG]]] bubbles this turn — not one lecture.]"
        )
    return (
        "[DIRECTOR: One message is fine. If the beat needs a pause, "
        "2 short [[[MSG]]] texts this turn.]"
    )


def join_beats(beats: list[str]) -> str:
    return "\n\n".join(b.strip() for b in beats if (b or "").strip())


def strip_msg_tags(text: str) -> str:
    cleaned = _MSG_BLOCK.sub(lambda m: (m.group(1) or "").strip(), text or "")
    cleaned = _MSG_TAG.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def split_bot_beats(
    text: str,
    *,
    room: str = "group",
    force: bool = False,
    max_beats: int = 3,
) -> list[str]:
    """One model output → 1–3 spoken bubbles. Tags never leak into chat."""
    raw = (text or "").strip()
    if not raw:
        return []
    tagged = [m.strip() for m in _MSG_BLOCK.findall(raw) if (m or "").strip()]
    if tagged:
        leftover = strip_msg_tags(_MSG_BLOCK.sub(" ", raw))
        beats = tagged
        if leftover and len(leftover) >= 16 and leftover not in beats:
            beats = [leftover, *beats]
        return _cap(beats, max_beats)

    cleaned = strip_msg_tags(raw)
    if not cleaned:
        return []
    if _KEEP_WHOLE.search(cleaned):
        return [cleaned]
    parts = [p.strip() for p in re.split(r"\n{2,}", cleaned) if p.strip()]
    if len(parts) < 2:
        return [cleaned]
    if force or _looks_like_separate_texts(parts):
        return _cap(parts, max_beats)
    _ = room
    return [cleaned]


def _looks_like_separate_texts(parts: list[str]) -> bool:
    if len(parts) < 2 or len(parts) > 4:
        return False
    addressed = sum(1 for p in parts if _ADDRESSED.search(p))
    if addressed >= 2:
        return True
    if all(12 <= len(p) <= 280 for p in parts) and all(
        p.endswith((".", "!", "?", "…", '"', ".”")) for p in parts
    ):
        return True
    return False


def _cap(parts: list[str], n: int) -> list[str]:
    out = [p.strip() for p in parts if (p or "").strip()]
    n = max(1, min(int(n or 3), 4))
    if len(out) <= n:
        return out
    return out[: n - 1] + [join_beats(out[n - 1 :])]
