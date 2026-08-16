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
_TONIGHT = re.compile(r"\btonight\b", re.I)
_FLAVOR = re.compile(
    r"\b("
    r"humiliation|cuck(?:old(?:ry|ing)?)?|cuck\s+fetish|"
    r"sph|cei|denial|chastity"
    r")\b",
    re.I,
)
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
    if _SESSION.search(text) or (
        _TONIGHT.search(text) and (_UNCAGE.search(text) or re.search(r"\bplay\b", text, re.I))
    ):
        out["session"] = "tonight"
    if _UNCAGE.search(text):
        out["cage"] = "off_for_play"
    if _EDGE.search(text):
        out["edge"] = "yes"
    if _KEEP_LOCKED.search(text):
        out["cage"] = "on"
    flavors = []
    for m in _FLAVOR.finditer(text):
        item = re.sub(r"\s+", " ", m.group(1).strip().lower())
        if item not in flavors:
            flavors.append(item)
    if flavors:
        out["flavors"] = ", ".join(flavors)
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
    if updates.get("flavors") and thread.get("flavors"):
        seen: list[str] = []
        for item in (
            str(thread.get("flavors") or "").split(",")
            + str(updates.get("flavors") or "").split(",")
        ):
            bit = item.strip()
            if bit and bit.lower() not in {x.lower() for x in seen}:
                seen.append(bit)
        updates = {**updates, "flavors": ", ".join(seen)}
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
    if thread.get("flavors"):
        bits.append("flavors: " + thread["flavors"])
    if not bits:
        return ""
    lines = [
        "[SCENE WE ARE ORGANISING — stay on this card; do not start a new scene]",
        "Her idea: " + "; ".join(bits) + ".",
        "Build the next beat on THIS scene. Do not invent chores, cold showers, "
        "or a different game unless she asked.",
        "Chaster remaining / 'until Tuesday' is the timer, not a veto. She holds the keys.",
        "She unlocks him. Never tell him to unlock himself.",
    ]
    if thread.get("cage") == "off_for_play" or thread.get("edge") == "yes":
        lines.append("Help her run the uncage / play / edge, then relock.")
    return "\n".join(lines)
