"""Guided scene interview: mode, duration, a few questions, then a keyholder guide."""

from __future__ import annotations

import re
from typing import Any

_CANCEL_RE = re.compile(
    r"\b("
    r"cancel(?:\s+the)?\s+scene|"
    r"stop\s+build(?:ing)?|"
    r"never\s+mind|"
    r"forget\s+(?:the\s+)?scene|"
    r"abort\s+(?:the\s+)?(?:scene|interview)"
    r")\b",
    re.I,
)

_MODE_VIRTUAL = re.compile(
    r"\b(virtual|remote|online|text(?:\s*only)?|over\s+text|not\s+(?:in[- ]person|together)|distance)\b",
    re.I,
)
_MODE_PERSON = re.compile(
    r"\b(in[- ]person|inperson|irl|together|same\s+room|with\s+me|face\s*to\s*face|physical)\b",
    re.I,
)

_DURATION_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?|hr)\b",
    re.I,
)
_LOCK_TIME_RE = re.compile(
    r"\b(add|remove|take\s+off|extend|subtract)\b",
    re.I,
)

_SKIP_RE = re.compile(
    r"\b(skip(?:\s+questions?)?|just\s+(?:write|build|make)\s+it|you\s+decide|surprise\s+me)\b",
    re.I,
)

_QUESTIONS = (
    (
        "mode",
        "Virtual or in-person? (this session only — I ask every time)",
    ),
    (
        "duration",
        "How long should this session last?",
    ),
    (
        "focus",
        "What should tonight lean on — denial, humiliation, impact, service — and anything off-limits?",
    ),
)


def empty_interview() -> dict[str, Any]:
    return {
        "active": False,
        "step": "mode",
        "mode": "",
        "duration": "",
        "focus": "",
    }


def start_interview() -> dict[str, Any]:
    iv = empty_interview()
    iv["active"] = True
    iv["step"] = "mode"
    return iv


def wants_cancel_interview(message: str) -> bool:
    return bool(_CANCEL_RE.search(message or ""))


def parse_mode(message: str) -> str:
    text = message or ""
    virt = bool(_MODE_VIRTUAL.search(text))
    person = bool(_MODE_PERSON.search(text))
    if virt and not person:
        return "virtual"
    if person and not virt:
        return "in_person"
    return ""


def parse_duration(message: str) -> str:
    text = message or ""
    if _LOCK_TIME_RE.search(text) and not re.search(
        r"\b(session|scene|play|long)\b", text, re.I
    ):
        return ""
    m = _DURATION_RE.search(text)
    if not m:
        return ""
    n = m.group(1)
    unit = m.group(2).lower()
    if unit.startswith("hour") or unit.startswith("hr"):
        label = "hour" if n in {"1", "1.0"} else "hours"
        return f"{n} {label}"
    label = "minute" if n in {"1", "1.0"} else "minutes"
    return f"{n} {label}"


def _next_missing(iv: dict[str, Any]) -> str:
    if not (iv.get("mode") or "").strip():
        return "mode"
    if not (iv.get("duration") or "").strip():
        return "duration"
    if not (iv.get("focus") or "").strip():
        return "focus"
    return "guide"


def apply_interview_answer(iv: dict[str, Any], message: str) -> dict[str, Any]:
    """Fill whatever we can parse from this Domme message, then set next step."""
    out = dict(iv or empty_interview())
    out["active"] = True
    text = (message or "").strip()
    if not text:
        out["step"] = _next_missing(out)
        return out

    mode = parse_mode(text)
    if mode:
        out["mode"] = mode
    dur = parse_duration(text)
    if dur:
        out["duration"] = dur

    leftover = text
    if mode:
        leftover = _MODE_VIRTUAL.sub("", leftover)
        leftover = _MODE_PERSON.sub("", leftover)
    if dur:
        leftover = _DURATION_RE.sub("", leftover)
    leftover = re.sub(r"\s+", " ", leftover).strip(" ,.-")
    if (
        leftover
        and not wants_scene_start_only(leftover)
        and not _LOCK_TIME_RE.search(leftover)
        and not _SKIP_RE.search(text)
    ):
        step = str(out.get("step") or "mode")
        if step == "focus" or (out.get("mode") and out.get("duration")):
            out["focus"] = leftover[:400]

    if _SKIP_RE.search(text):
        out.setdefault("mode", out.get("mode") or "")
        if not out.get("duration"):
            out["duration"] = "45 minutes"
        if not out.get("focus"):
            out["focus"] = "Use the session kit; denial-first; stay in hard limits."

    out["step"] = _next_missing(out)
    if out["step"] == "guide":
        out["active"] = False
    return out


def wants_scene_start_only(message: str) -> bool:
    """True if the line is mostly 'build a scene' with no extra answers."""
    text = re.sub(r"\s+", " ", (message or "").strip())
    return bool(
        re.fullmatch(
            r"(please\s+)?(help\s+me\s+)?(build|create|write|plan|make)"
            r"(\s+me)?(\s+a)?\s+(scene|session)(\s+guide)?[?.!]*",
            text,
            re.I,
        )
    )


def current_question(iv: dict[str, Any]) -> str:
    step = str((iv or {}).get("step") or "mode")
    for key, q in _QUESTIONS:
        if key == step:
            return q
    return ""


def format_interview_director(iv: dict[str, Any], *, room: str = "private") -> str:
    step = str(iv.get("step") or "mode")
    question = current_question(iv)
    filled = []
    if iv.get("mode"):
        filled.append(f"mode={iv['mode']}")
    if iv.get("duration"):
        filled.append(f"duration={iv['duration']}")
    if iv.get("focus"):
        filled.append(f"focus={iv['focus']}")
    have = ", ".join(filled) or "nothing yet"
    where = (
        "Ask the human Domme by NAME. One question only. Do not write the scene yet. "
        "Do not emit GROUP tags."
        if room == "private"
        else "Ask the keyholder this one question. Do not run a scene on him yet. "
        "Do not invent what he is doing."
    )
    return (
        "\n\n[SCENE INTERVIEW — still collecting]\n"
        f"Already have: {have}\n"
        f"Ask ONLY this: {question}\n"
        f"{where}\n"
        "Do not roleplay both sides. Do not invent bathroom/location/body events.\n"
        f"Step={step}. After she answers, wait — do not dump a full guide this turn.\n"
    )


def format_guide_director(
    iv: dict[str, Any],
    *,
    toys: list[str],
    kinks: list[str],
    room: str = "private",
) -> str:
    mode = iv.get("mode") or "virtual"
    duration = iv.get("duration") or "45 minutes"
    focus = iv.get("focus") or "tease and denial"
    toy_txt = ", ".join(toys) or "(session kit / his listed toys)"
    kink_txt = ", ".join(kinks) or "chastity, tease and denial"
    if mode == "in_person":
        mode_rules = (
            "IN-PERSON: she is with him. Toys can be used in her hands. "
            "Give timed beats she can follow in the room. Watch circulation, breathing, safeword."
        )
    else:
        mode_rules = (
            "VIRTUAL: they are not in the same room. Guide uses text, photos, voice, "
            "and lock levers only. Do not assume she can physically paddle/gag him. "
            "If a toy is listed, tell her to have HIM fetch/wear it or describe it — "
            "not that she is holding it unless she said so."
        )
    where = (
        "Write the guide TO the human Domme by NAME. This is her script to carry out. "
        "Do not pretend it is happening live. No GROUP tags unless she asked to start now."
        if room == "private"
        else "Write a short keyholder guide she can follow. Do not act it out as if he "
        "already did the beats. Do not invent what he is doing right now."
    )
    return (
        "\n\n[SCENE GUIDE — write the session plan now]\n"
        f"Mode: {mode}\n"
        f"Duration: {duration}\n"
        f"Focus from her: {focus}\n"
        f"Toys to incorporate: {toy_txt}\n"
        f"Kink hooks: {kink_txt}\n"
        f"{mode_rules}\n"
        "OUTPUT as a KEYHOLDER SESSION GUIDE with:\n"
        "  - Setup (1-2 lines)\n"
        "  - Timed beats covering the duration (setup → tease → denial → close)\n"
        "  - What she says/does vs what he must do\n"
        "  - How to leave him horny and submissive at the end (no orgasm unless she said so)\n"
        "  - Safety / safeword reminder\n"
        f"{where}\n"
        "HARD RULES:\n"
        "- Speak only as yourself. Never write BOY: / Keyholder: scripted dialogue.\n"
        "- Do not invent events that nobody typed (toilet, meals, travel, touching).\n"
        "- Do not invent toys outside the list.\n"
        "- Stay inside hard limits.\n"
    )
