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
_WINDOW = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m)\b",
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
    unlocked = bool(
        _UNCAGE.search(text)
        or re.search(r"\bunlocked\b", text, re.I)
        or re.search(
            r"\b(hour outside|outside of (?:it|the cage)|out of the cage)\b",
            text,
            re.I,
        )
    )
    if unlocked:
        out["cage"] = "off_for_play"
    if _SESSION.search(text) or (
        _TONIGHT.search(text)
        and (unlocked or re.search(r"\bplay\b", text, re.I))
    ):
        out["session"] = "tonight"
    if _EDGE.search(text):
        out["edge"] = "yes"
    if re.search(r"\btease him\b", text, re.I):
        out["tease"] = "yes"
    if _KEEP_LOCKED.search(text):
        out["cage"] = "on"
    flavors = []
    for m in _FLAVOR.finditer(text):
        item = re.sub(r"\s+", " ", m.group(1).strip().lower())
        if item not in flavors:
            flavors.append(item)
    if flavors:
        out["flavors"] = ", ".join(flavors)
    from app.play_session import parse_play_rate

    rate = parse_play_rate(text)
    if rate is not None:
        out["debt_rate"] = "off" if rate <= 0 else f"{rate:g}"
    if out.get("cage") == "off_for_play" or _TONIGHT.search(text):
        for wm in _WINDOW.finditer(text):
            after = text[wm.end() : wm.end() + 24]
            if re.search(r"^\s*(?:locked\s+)?per\s+(?:each\s+)?min", after, re.I):
                continue
            n = wm.group(1)
            unit = wm.group(2).lower()
            label = "hour" if unit.startswith("h") else "minute"
            if float(n) != 1:
                label += "s"
            out["window"] = f"{n} {label}"
            break
    if not out.get("window") and (
        out.get("cage") == "off_for_play" or _TONIGHT.search(text)
    ):
        if re.search(r"\b(?:an|one)\s+hours?\b", text, re.I):
            out["window"] = "1 hour"
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
    if thread.get("tease") == "yes":
        bits.append("tease him while uncaged")
    if thread.get("window"):
        bits.append("unlock window " + thread["window"])
    if thread.get("flavors"):
        bits.append("flavors: " + thread["flavors"])
    if thread.get("kink"):
        bits.append("use kink " + thread["kink"])
    if thread.get("toy"):
        bits.append("use toy " + thread["toy"])
    try:
        from app.play_session import snapshot as play_snap

        st = play_snap()
        rate = float(st.get("rate") or 0)
        if rate > 0:
            bits.append(f"price {rate:g} min locked per min out")
        elif thread.get("debt_rate") == "off":
            bits.append("no time price")
        if st.get("status") == "running":
            bits.append("play timer running")
    except Exception:  # noqa: BLE001
        if thread.get("debt_rate") and thread.get("debt_rate") != "off":
            bits.append(f"price {thread['debt_rate']} min locked per min out")
        elif thread.get("debt_rate") == "off":
            bits.append("no time price")
    if not bits:
        return ""
    lines = [
        "[SCENE WE ARE ORGANISING — stay on this card; do not start a new scene]",
        "Her idea: " + "; ".join(bits) + ".",
    ]
    if thread.get("cage") == "off_for_play" or thread.get("window"):
        lines.extend(
            [
                "GAME ORDER — do not invert this:",
                "1. Uncage him. The hour is PLAY time, not lock time.",
                "2. The game is what SHE does to him while he is out "
                "(tease, humiliation, cuck, edge).",
                "3. Lock him at the END of the game.",
                "Do NOT make the Chaster timer, a hidden lock, or 'lock him as the game' "
                "the activity. She may still change her mind and not unlock him — "
                "that is a mind-game option, not the default plan.",
                "Do NOT suggest 1 minute added per minute out — that is not a price. "
                "A price is 2 min locked per min out (or the rate she names). "
                "Time her Unlock to Lock. The system adds it. No LOCK tags for this.",
            ]
        )
    else:
        lines.append(
            "Build the next beat on THIS scene. Do not invent a different game unless she asked."
        )
    lines.append(
        "Chaster remaining is the long lock, not tonight's game. She holds the keys. "
        "Never tell him to unlock himself."
    )
    return "\n".join(lines)
