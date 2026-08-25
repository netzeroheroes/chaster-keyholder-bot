"""Keyholder hands the bot the lock — talk like a person, then actually run him."""

from __future__ import annotations

import re
from typing import Any

_START_RE = re.compile(
    r"\b("
    r"take control(?: of him)?|"
    r"take charge(?: of him)?|"
    r"take over(?: (?:with |of )?him)?|"
    r"you('?re| are) in charge|"
    r"you take (?:control|charge|over)|"
    r"(?:you |just )?handle him|"
    r"run him(?: for me)?|"
    r"he'?s yours|"
    r"do what you want with him|"
    r"you (?:deal with|look after|manage) him|"
    r"in charge of him|"
    r"be (?:his |the )?(?:keyholder|dom(?:me)?) for (?:me|a (?:bit|while|night))|"
    r"you run (?:the lock|him)"
    r")\b",
    re.I,
)

_GO_RE = re.compile(
    r"\b("
    r"go(?: ahead)?|"
    r"do it(?: now)?|"
    r"start(?: now)?|"
    r"tell him|"
    r"take him|"
    r"he'?s yours(?: now)?|"
    r"surprise me|"
    r"you decide|"
    r"just (?:do it|take (?:over|him|control))|"
    r"yes,? (?:take|do|run)|"
    r"have him"
    r")\b",
    re.I,
)

_CANCEL_RE = re.compile(
    r"\b("
    r"i('?ve| have) got him|"
    r"i('?ll| will) take him back|"
    r"stop (?:controlling|running) him|"
    r"i('?m| am) back|"
    r"my lock again|"
    r"cancel(?: the)? (?:handoff|takeover|control)"
    r")\b",
    re.I,
)


def empty_handoff() -> dict[str, Any]:
    return {"active": False, "phase": "idle"}


def wants_handoff(message: str) -> bool:
    return bool(_START_RE.search(message or ""))


def wants_handoff_go(message: str) -> bool:
    return bool(_GO_RE.search(message or ""))


def wants_handoff_cancel(message: str) -> bool:
    return bool(_CANCEL_RE.search(message or ""))


def start_handoff() -> dict[str, Any]:
    return {"active": True, "phase": "pitch"}


def apply_handoff(state: dict[str, Any], message: str) -> dict[str, Any]:
    out = dict(state or empty_handoff())
    if not out.get("active"):
        return out
    if wants_handoff_cancel(message):
        return empty_handoff()
    if wants_handoff_go(message):
        out["phase"] = "running"
        out["active"] = True
        return out
    if out.get("phase") == "pitch" and not wants_handoff(message):
        out["phase"] = "shaping"
    return out


def _context_lines(memory: Any, scene: Any) -> list[str]:
    lines: list[str] = []
    kinks = [str(x).strip() for x in (getattr(memory, "kinks", None) or []) if str(x).strip()]
    toys = [str(x).strip() for x in (getattr(scene, "session_toys", None) or []) if str(x).strip()]
    kit_kinks = [str(x).strip() for x in (getattr(scene, "session_kinks", None) or []) if str(x).strip()]
    ons = [str(x).strip() for x in (getattr(memory, "her_turn_ons", None) or []) if str(x).strip()]
    if kit_kinks:
        lines.append("Session kit kinks: " + ", ".join(kit_kinks[-8:]))
    elif kinks:
        lines.append("His kinks: " + ", ".join(kinks[-8:]))
    if toys:
        lines.append("Toys in play: " + ", ".join(toys[-8:]))
    if ons:
        lines.append("What turns HER on (use on him): " + ", ".join(ons[-6:]))
    return lines


def format_handoff_director(
    state: dict[str, Any],
    *,
    room: str,
    memory: Any = None,
    scene: Any = None,
) -> str:
    phase = str((state or {}).get("phase") or "pitch")
    ctx = "\n".join(_context_lines(memory, scene))
    ctx_bit = f"\nKnown to use (do not dump as a list to her):\n{ctx}" if ctx else ""

    if phase == "running":
        if room == "group":
            return (
                "[DIRECTOR: You are running him. She handed you the lock. "
                "Unlock and orgasm stay hers unless she typed otherwise. "
                "Talk like a person in charge — specific, one beat, a question that puts him on the back foot. "
                "Do not ask him what he wants. Do not recap the plan. Do not check with her every line.]"
            )
        return (
            "[DIRECTOR: You are running him. Talk to HER about how it's going. "
            "[[[GROUP]]] only when there is a real next beat for him. "
            "Unlock/orgasm stay hers.]"
        )

    if room == "group":
        return (
            "[DIRECTOR: She asked you to take control. Do NOT plan in front of him. "
            "One short Group line — you've got him, stay locked — then the real talk is with HER. "
            "No questionnaire. No lock dump.]"
        )

    if phase == "shaping":
        return (
            "[DIRECTOR: She is handing you control. This is a human conversation, not a form.\n"
            "She just answered. Build from THAT. Do not restart. Do not numbered menu.\n"
            "Offer one sharper beat you would actually run, then ask one thing you still need "
            "(what she keeps vs what you may do without asking — unlock and orgasm default to hers).\n"
            "If she already said go / do it / tell him: first move on him via [[[GROUP]]].]"
            f"{ctx_bit}"
        )

    return (
        "[DIRECTOR: She asked you to TAKE CONTROL of him. Be a person who wants this — "
        "her co-keyholder, hungry, not a secretary.\n"
        "Do NOT dump a questionnaire (no virtual/in-person/how-long form). "
        "Do NOT instantly punish, add time, or [[[LOCK]]] unless she already named that beat.\n"
        "Sound like a friend who is taking the leash:\n"
        "1. Yes — you want him. One or two sentences, specific heat.\n"
        "2. Suggest 2–3 things YOU could take charge of (drawn from kit / his kinks / her turn-ons if known). "
        "Examples: talking to him in Group as the one running tonight; teases on a rhythm; "
        "adding time when he brats; a game; grilling him for buttons; using what turns her on against him.\n"
        "3. Ask ONE real question: what she wants to keep (keys, orgasm, hard no's) vs what you may do without pinging her.\n"
        "Wait. Do not start on him until she says go / do it / tell him / he's yours.\n"
        "Never 'noted' or 'as an AI'."
        f"{ctx_bit}"
    )
