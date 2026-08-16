"""Private play thread: stay on her idea (uncage / edge / tease). Timer is not a veto."""

from __future__ import annotations

import re
from typing import Any

_SESSION = re.compile(
    r"\b(play session|session tonight|ideas for (?:a )?play|tonight'?s session)\b",
    re.I,
)
_UNCAGE = re.compile(
    r"\b("
    r"uncage(?:d| him)?|"
    r"let him out|"
    r"let him out for|"
    r"take (?:the |his )?cage off|"
    r"unlock him|"
    r"out for (?:some )?teas"
    r")\b",
    re.I,
)
_EDGE = re.compile(r"\bedge(?:d| him| me)?\b", re.I)
_KEEP_LOCKED = re.compile(
    r"\b("
    r"keep him locked|stay locked|leave him locked|"
    r"don'?t (?:let him out|unlock)|"
    r"just locked(?: him)?|"
    r"locked him back|"
    r"back in the cage"
    r")\b",
    re.I,
)


def parse_play_updates(message: str) -> dict[str, str]:
    text = message or ""
    out: dict[str, str] = {}
    if _SESSION.search(text):
        out["session"] = "tonight"
    if _UNCAGE.search(text):
        out["cage"] = "off_for_play"
    if _EDGE.search(text):
        out["edge"] = "yes"
    if _KEEP_LOCKED.search(text):
        out["cage"] = "on"
    return out


BOX_BUTTON_LINES = {
    "unlock": (
        "I just unlocked the box. He's uncaged. "
        "Help me play with him — tease him."
    ),
    "lock": (
        "I just locked him back in the cage. "
        "Keep going — tease him."
    ),
}


def box_button_message(action: str) -> str | None:
    """Spoken line when she taps Unlock / Lock — starts a Private turn + Group tease."""
    return BOX_BUTTON_LINES.get((action or "").strip().lower())


def wants_uncage_play(message: str) -> bool:
    bits = parse_play_updates(message)
    return bits.get("cage") == "off_for_play" or "edge" in bits


def apply_play_updates(scene: Any, updates: dict[str, str]) -> dict[str, str]:
    if not updates:
        return {}
    thread = dict(getattr(scene, "play_thread", None) or {})
    thread.update(updates)
    scene.update(play_thread=thread)
    return updates


def format_play_block(scene: Any, *, this_turn: dict[str, str] | None = None) -> str:
    thread = dict(getattr(scene, "play_thread", None) or {})
    if this_turn:
        thread = {**thread, **this_turn}
    if not thread:
        return ""
    bits: list[str] = []
    if thread.get("session"):
        bits.append("play session tonight")
    if thread.get("cage") == "off_for_play":
        bits.append("she wants him UNCAGED to play")
    elif thread.get("cage") == "on":
        bits.append("keep him locked")
    if thread.get("edge") == "yes":
        bits.append("edge him")
    if not bits:
        return ""
    lines = [
        "[PLAY THREAD — stay on this; do not reset to 'he has to stay locked']",
        "Her idea: " + "; ".join(bits) + ".",
        "Chaster remaining / 'until Tuesday' is the timer, not a veto. She holds the keys.",
        "She unlocks him. Never tell him to unlock himself.",
    ]
    if thread.get("cage") == "off_for_play" or thread.get("edge") == "yes":
        lines.append(
            "Help her run the uncage / tease / edge, then relock. "
            "Do not change the subject back to staying locked."
        )
    return "\n".join(lines)
