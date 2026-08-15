"""Strict guards against inventing Chaster lock numbers in chat replies."""

from __future__ import annotations

import re

# Claims that imply a lock change or fake numeric lock state
_LOCK_CLAIM = re.compile(
    r"("
    r"\bnew length\b|"
    r"\btotal time locked\b|"
    r"\b\d+\s*\+\s*\d+\s*=\s*\d+\s*days?\b|"
    r"\block type:\b|"
    r"\bkeypad\b|"
    r"\bnew sequence\b|"
    r"\b(?:added|removed|extended)\b.{0,50}\b"
    r"(?:\d+|a|one|two|three|another)\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?)\b|"
    r"\b(?:\d+|one|two|three|four|five|ten|fifteen|thirty)\s+"
    r"(?:days?|hours?)\b.{0,40}\b(?:left|remaining|on (?:your|his) (?:lock|cage)|locked now)\b"
    r")",
    re.I,
)

_LOCK_TAG = re.compile(r"\[\[\[/?LOCK\]\]\]", re.I)


def looks_like_lock_hallucination(text: str, *, had_action_facts: bool) -> bool:
    """True if the model invents lock numbers/changes without API confirmation."""
    if not (text or "").strip() or had_action_facts:
        return False
    # LOCK tags mean a real action path will run — leave those for execution
    if _LOCK_TAG.search(text):
        return False
    return bool(_LOCK_CLAIM.search(text))


_CLAIM_SENTENCE = re.compile(
    r"[^.!?\n]*("
    + _LOCK_CLAIM.pattern
    + r")[^.!?\n]*[.!?]?",
    re.I,
)

_JOURNEY_FALLBACK = (
    "Maybe if you earn it. Stay with that ache — I'll talk to her about what comes next."
)


def _strip_lock_claim_sentences(text: str) -> str:
    cleaned = _CLAIM_SENTENCE.sub("", text or "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()
    return cleaned


def scrub_lock_hallucinations(
    text: str,
    *,
    live_remaining: str = "",
    had_action_facts: bool,
) -> str | None:
    """
    Drop invented lock-number sentences. Keep the tease.
    Returns None when the original text is acceptable.
    """
    if not looks_like_lock_hallucination(text, had_action_facts=had_action_facts):
        return None
    cleaned = _strip_lock_claim_sentences(text)
    if cleaned and len(cleaned) >= 20:
        return cleaned
    return _JOURNEY_FALLBACK
