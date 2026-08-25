"""Keyholder hands the bot the lock — talk like a person, then actually run him."""

from __future__ import annotations

import re
from typing import Any

_START_RE = re.compile(
    r"\b("
    r"take control(?: of him)?|"
    r"take charge(?: of him)?|"
    r"take over(?: (?:with |of )?him)?|"
    r"take the lead|"
    r"you take the lead|"
    r"you('?re| are) in charge|"
    r"you('?re| are) the lead|"
    r"you('?re| are) running(?: things)?|"
    r"you('?re| are) runnng things|"
    r"run(?:ning|nng) things(?: today| tonight)?|"
    r"you take (?:control|charge|over)|"
    r"(?:you |just )?handle him|"
    r"run him(?: for me)?|"
    r"he'?s yours|"
    r"do what you want with him|"
    r"you (?:deal with|look after|manage) him|"
    r"in charge of him|"
    r"be (?:his |the )?(?:keyholder|dom(?:me)?) for (?:me|a (?:bit|while|night))|"
    r"you run (?:the lock|him|things)|"
    r"he'?s both of our toys|"
    r"both of our toys|"
    r"our toy now|"
    r"he (?:doesn'?t|does not|dosnt) get a say"
    r")\b",
    re.I,
)

_LEAD_NOW_RE = re.compile(
    r"\b("
    r"take the lead|"
    r"you take the lead|"
    r"you('?re| are) (?:in charge|the lead|running(?: things)?|runnng things)|"
    r"run(?:ning|nng) things(?: today| tonight)?|"
    r"you run things|"
    r"he'?s yours(?: now)?|"
    r"both of our toys|"
    r"our toy now|"
    r"he (?:doesn'?t|does not|dosnt) get a say|"
    r"you decide|"
    r"surprise me"
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
    return bool(_START_RE.search(message or "")) or wants_lead_now(message)


def wants_lead_now(message: str) -> bool:
    """She already handed the leash — start, do not interview her."""
    return bool(_LEAD_NOW_RE.search(message or ""))


def wants_handoff_go(message: str) -> bool:
    return bool(_GO_RE.search(message or ""))


def wants_handoff_cancel(message: str) -> bool:
    return bool(_CANCEL_RE.search(message or ""))


def start_handoff() -> dict[str, Any]:
    return {"active": True, "phase": "running"}


def apply_handoff(state: dict[str, Any], message: str) -> dict[str, Any]:
    out = dict(state or empty_handoff())
    if wants_handoff_cancel(message):
        return empty_handoff()
    if wants_lead_now(message) or wants_handoff(message) or wants_handoff_go(message):
        out["active"] = True
        out["phase"] = "running"
        return out
    if not out.get("active"):
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
    ctx = "\n".join(_context_lines(memory, scene))
    ctx_bit = f"\nKnown to use (do not dump as a list to her):\n{ctx}" if ctx else ""
    if room == "group":
        return (
            "[DIRECTOR: She handed you the lead. START NOW.\n"
            "Ack her in one short clause. Then talk TO him. One specific beat — "
            "an order or a tease he has to sit with.\n"
            "Do NOT ask her where to begin / what she wants to do / any ideas.\n"
            "Do NOT ask him what he wants. Do not recap the plan. Unlock and orgasm stay hers "
            "unless she typed otherwise. If you are her bull: you are with his girl; he waits.]"
            f"{ctx_bit}"
        )
    return (
        "[DIRECTOR: She handed you the lead. Do NOT ask where to begin.\n"
        "Start the beat yourself. If you are her bull, start with HER. "
        "Then [[[GROUP]]] one line at him. Unlock/orgasm stay hers.]"
        f"{ctx_bit}"
    )


def format_lead_now_group_line(
    *,
    bull_voice: bool = False,
    title: str = "",
    sub_name: str = "",
) -> str:
    her = (title or "Keyholder").strip() or "Keyholder"
    sub = (sub_name or "Lockee").strip() or "Lockee"
    if bull_voice:
        return (
            f"{her} — I've got him.\n\n"
            f"{sub} — you're both of our toys today. No vote. "
            "Hands on the cage. She's with me. Stay locked. Begin."
        )
    return (
        f"{her} — I've got him.\n\n"
        f"{sub} — you're ours. Stay locked. Hands on the cage. "
        "You don't pick who leads. Start now."
    )
