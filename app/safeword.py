"""Safewords are system commands — halt the scene, do not play them as flavor."""

from __future__ import annotations

import re
from typing import Literal

Safeword = Literal["red", "yellow"]

_STANDALONE = re.compile(
    r"^\s*(?:(?:ooc|out of character)\s*[:\-]\s*)?"
    r"(red|yellow|safeword|safe\s*word)"
    r"(?:\s*(?:please|now)?)?"
    r"\s*[.!]?\s*$",
    re.I,
)
_PHRASE = re.compile(
    r"\b("
    r"i(?:'m| am) (?:using |calling |hitting )?(?:my )?safeword|"
    r"(?:use|using|call|calling|hit|hitting) (?:my )?safeword|"
    r"safeword(?: is|:)?\s*red"
    r")\b",
    re.I,
)


def safeword_level(message: str) -> Safeword | None:
    """Red / yellow only when they meant the traffic-light, not 'red dress'."""
    text = (message or "").strip()
    if not text:
        return None
    m = _STANDALONE.match(text)
    if m:
        token = re.sub(r"\s+", " ", m.group(1).lower())
        if token == "yellow":
            return "yellow"
        return "red"
    if _PHRASE.search(text):
        return "red"
    return None


def safeword_director(level: Safeword, *, room: str, role: str) -> str:
    if level == "yellow":
        return (
            "[DIRECTOR: YELLOW. Slow down. Check in. Do not escalate, pile on, "
            "or add a new humiliation. Ask if they want to continue, pause, or stop. "
            "Unlock stays hers.]"
        )
    if role == "sub":
        who = "him" if (room or "") == "group" else "them"
        return (
            "[DIRECTOR: SAFEWORD / RED. Scene HALTS NOW. "
            f"Warm check-in with {who}. No tease, no orders, no 'continue'. "
            "Aftercare. The lock can stay; the scene does not. "
            "If Group: one short line here, then she gets the rest in Private.]"
        )
    if (room or "") == "private":
        return (
            "[DIRECTOR: SAFEWORD / RED. Scene HALTS NOW. "
            "Break the Dom voice. Warm, specific aftercare with HER. "
            "Reference what just happened. No titles, no tease, no next beat.]"
        )
    return (
        "[DIRECTOR: SAFEWORD / RED. Scene HALTS NOW. "
        "Soft check-in. No tease. No running him. Aftercare. "
        "Unlock stays hers unless she types it.]"
    )
