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


def scrub_lock_hallucinations(
    text: str,
    *,
    live_remaining: str = "",
    had_action_facts: bool,
) -> str | None:
    """
    If the reply invents lock state without API action facts, return a corrected reply.
    Returns None when the original text is acceptable.
    """
    if not looks_like_lock_hallucination(text, had_action_facts=had_action_facts):
        return None
    rem = live_remaining or "whatever Chaster shows right now"
    return (
        "Your lock numbers come from Chaster - I don't invent them.\n\n"
        f"Live remaining: {rem}. "
        "No fake day totals, keypad codes, or 'new lengths'. "
        "Mistress and I change the real lock when we decide."
    )
