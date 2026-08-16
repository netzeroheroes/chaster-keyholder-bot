"""Cage-aware keyholder practice — he cannot stroke while locked."""

from __future__ import annotations

import re

# Distilled from common chastity / tease-and-denial keyholder practice:
# anticipation and denial beat genital access; the cage is the point.
PRACTICE_BLOCK = """
[CAGE PRACTICE]
While he is caged he cannot stroke — do not order that.
If SHE wants him uncaged to tease or edge, follow her. Remaining time is not a veto.
She unlocks him. Never tell him to unlock himself.
Do not assume he obeyed or how he feels unless he typed it.
"""

_CAGED_TOUCH = re.compile(
    r"[^.!?\n]*\b("
    r"touch yourself|"
    r"stroke(?:\s+your(?:self| cock| dick| shaft))?|"
    r"jerk(?:\s+off)?|"
    r"masturbat\w*|"
    r"hands on your (?:cock|dick|shaft)|"
    r"play with yourself|"
    r"go ahead and touch|"
    r"keep it gentle"
    r")\b[^.!?\n]*[.!?]?",
    re.I,
)

_TEASE_SWAP = (
    "The cage stays on — you don't get to touch. Sit with that ache and thank us for it."
)


def orders_caged_touch(text: str) -> bool:
    return bool(_CAGED_TOUCH.search(text or ""))


def rewrite_caged_touch(text: str) -> str:
    """Turn impossible stroke/touch orders into cage tease."""
    if not orders_caged_touch(text):
        return text or ""
    cleaned = _CAGED_TOUCH.sub("", text or "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()
    if not cleaned or len(cleaned) < 12:
        return _TEASE_SWAP
    if _TEASE_SWAP.lower() not in cleaned.lower():
        return f"{cleaned}\n\n{_TEASE_SWAP}"
    return cleaned
