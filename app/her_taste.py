"""Keyholder pleasure: orgasm ratings, turn-ons, fantasies — used on the lockee."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.session_kit import clean_names

_ORGASM_RE = re.compile(
    r"\b("
    r"(?:i(?:'ve| have)?\s+)?(?:just\s+)?(?:came|orgasm(?:ed)?)\b|"
    r"rate(?:d|ing)?\s+(?:my\s+)?orgasm|"
    r"orgasm\s+(?:rating|was)|"
    r"it was (?:a\s+)?"
    r")\s*.{0,24}?(?P<n>10|[1-9])(?:\s*/\s*10)?",
    re.I,
)
_RATING_LINE = re.compile(
    r"\borgasm\s+rating\s*[:\s]+(?P<n>10|[1-9])(?:\s*/\s*10)?",
    re.I,
)
_SCORE_ONLY = re.compile(r"\b(?P<n>10|[1-9])\s*/\s*10\b", re.I)

_TURN_ON_RE = re.compile(
    r"\b("
    r"turns? me on|"
    r"i get off on|"
    r"i(?:'m| am) into|"
    r"i love when|"
    r"i like when|"
    r"what gets me (?:off|wet|horny)|"
    r"my (?:turn[- ]?ons?)"
    r")\b[:\s]+(.{3,240})",
    re.I,
)
_FANTASY_RE = re.compile(
    r"\b("
    r"my fantasy|"
    r"fantas(?:y|ies)|"
    r"i fantasize|"
    r"i want you to|"
    r"use (?:him|the lock) (?:for|on) me"
    r")\b[:\s]+(.{3,240})",
    re.I,
)

_HER_ASK = re.compile(
    r"\b("
    r"what turns me on|"
    r"learn (?:what )?i (?:like|want)|"
    r"learn (?:me|my)|"
    r"ask me (?:what i like|about me|what turns me on)|"
    r"my turn[- ]?ons|"
    r"help (?:you )?learn (?:me|what i like)"
    r")\b",
    re.I,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def clamp_rating(raw: Any) -> int | None:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    if 1 <= n <= 10:
        return n
    return None


def parse_orgasm_rating(message: str) -> int | None:
    text = message or ""
    for rx in (_RATING_LINE, _ORGASM_RE):
        m = rx.search(text)
        if m:
            return clamp_rating(m.group("n"))
    if re.search(r"\b(came|orgasm)\b", text, re.I):
        sm = _SCORE_ONLY.search(text)
        if sm:
            return clamp_rating(sm.group("n"))
    return None


def parse_her_taste(message: str) -> dict[str, list[str]]:
    text = message or ""
    out: dict[str, list[str]] = {}
    tm = _TURN_ON_RE.search(text)
    if tm:
        items = clean_names(re.split(r"\s*(?:,|;|/|\band\b)\s*", tm.group(2)))
        if items:
            out["her_turn_ons"] = items[:8]
    fm = _FANTASY_RE.search(text)
    if fm:
        items = clean_names(re.split(r"\s*(?:,|;)\s*", fm.group(2)))
        if items:
            out["her_fantasies"] = items[:8]
    return out


def wants_her_taste(message: str) -> bool:
    return bool(_HER_ASK.search(message or ""))


def apply_her_taste(memory: Any, updates: dict[str, list[str]]) -> dict[str, list[str]]:
    if not updates:
        return {}
    fields: dict[str, list[str]] = {}
    for key, items in updates.items():
        cur = [str(x) for x in (getattr(memory, key, None) or []) if str(x).strip()]
        seen = {x.lower() for x in cur}
        for item in items:
            low = item.lower()
            if low not in seen:
                cur.append(item)
                seen.add(low)
        fields[key] = cur[-40:]
    memory.update_fields(**fields)
    return updates


def record_orgasm(
    memory: Any,
    rating: int,
    *,
    note: str = "",
    tell_him: bool = False,
) -> dict[str, Any]:
    score = clamp_rating(rating)
    if score is None:
        return {}
    log = list(getattr(memory, "her_orgasms", None) or [])
    entry = {
        "when": _now(),
        "rating": str(score),
        "note": (note or "").strip()[:240],
        "tell_him": bool(tell_him),
    }
    log.append(entry)
    memory.update_fields(her_orgasms=log[-40:])
    return entry


def last_orgasm(memory: Any) -> dict[str, str]:
    log = list(getattr(memory, "her_orgasms", None) or [])
    if not log:
        return {}
    last = log[-1]
    if not isinstance(last, dict):
        return {}
    return {
        "when": str(last.get("when") or ""),
        "rating": str(last.get("rating") or ""),
        "note": str(last.get("note") or ""),
        "tell_him": bool(last.get("tell_him")),
    }


def format_her_taste_block(memory: Any, *, room: str = "private") -> str:
    ons = clean_names(getattr(memory, "her_turn_ons", None) or [])
    fantasies = clean_names(getattr(memory, "her_fantasies", None) or [])
    last = last_orgasm(memory)
    if not ons and not fantasies and not last:
        return ""
    lines = [
        "[HER PLEASURE — the lock exists to serve HER, not him]",
        "Use what you know about her to shape his lock, tease, and cuck/bull energy.",
        "Never treat her as the sub. Never rate or demand her orgasm in Group unless she asked.",
    ]
    if ons:
        lines.append("What turns her on: " + ", ".join(ons[-12:]))
    if fantasies:
        lines.append("Her fantasies: " + ", ".join(fantasies[-12:]))
    if last.get("rating"):
        extra = f" — {last['note']}" if last.get("note") else ""
        lines.append(
            f"Last orgasm she logged: {last['rating']}/10 ({last.get('when') or 'recent'}){extra}."
        )
        if last.get("tell_him") in (True, "true", "1"):
            lines.append("He was told the score.")
        else:
            lines.append(
                "He was only told she came — not the number. Do not quote her rating in Group."
            )
    if room == "group":
        lines.append(
            "GROUP: Do not dump this list. Use it quietly on him. "
            "If she just came, gloat at him — she is not the one locked."
        )
    return "\n".join(lines)


def format_orgasm_director(rating: int, *, note: str = "", room: str = "private") -> str:
    score = clamp_rating(rating) or 5
    note_bit = f" Her note: {note.strip()[:200]}." if (note or "").strip() else ""
    bull = False
    try:
        from app.bot_persona import is_bull_voice

        bull = is_bull_voice()
    except Exception:  # noqa: BLE001
        bull = False
    if score >= 8:
        treat = (
            "HIGH. She came hard. He did not. Rub it in. Keep him locked. "
            "Stack the next beat around what just worked for HER "
            "(bull/cuck, denial, service). A crumb of warmth is optional — never unlock."
        )
    elif score >= 5:
        treat = (
            "MID. It was fine, not enough. Ask her (privately) what would have pushed it higher. "
            "On him: hungrier, more specific, use her turn-ons. He stays denied."
        )
    else:
        treat = (
            "LOW. Her body first — check she is ok, no pile-on tease at her. "
            "Then use it on HIM: he wasn't enough, the lock wasn't serving her. "
            "Offer one concrete next beat from her fantasies. Do not punish her."
        )
    if room == "private":
        if bull:
            where = (
                "You are her BULL. You were with her. Talk to HER — hungry, specific. "
                "Do not bounce to a lock-tease briefing. "
                "He is being told she came, NOT the number. Do not emit [[[GROUP]]] yourself."
            )
        else:
            where = (
                "Talk to HER. Plan how to use this on him. "
                "He is being told she came, not the score. Do not emit [[[GROUP]]] yourself."
            )
    else:
        where = (
            "One mean line to him about her orgasm — no numbers lecture. "
            "She is the one who came. He waits."
        )
        if bull:
            where = (
                "You are the bull. One mean line: she came with you. He is locked. "
                "He waits. Do not unlock."
            )
    return (
        f"[HER ORGASM — she rated it {score}/10.{note_bit}]\n"
        f"{treat}\n"
        f"{where}\n"
        "Stay in hard limits. Unlock stays hers."
    )


def format_orgasm_lockee_notice(*, bull_voice: bool = False) -> str:
    """Group line when she logged an orgasm in Private — no score, no note."""
    if bull_voice:
        return (
            "She just came. You're still locked. "
            "You don't get the details — I was with her. Sit with that."
        )
    return (
        "She just came. You're still locked. "
        "You don't get the details. Wait."
    )


def format_learn_her_director(*, room: str = "private") -> str:
    if room == "private":
        return (
            "[DIRECTOR: Learn HER. Ask one thing — what turns her on, a fantasy, "
            "how she wants the lock used for her pleasure. Store it. "
            "Do not grill him this turn.]"
        )
    return (
        "[DIRECTOR: She wants you to learn her. Do that in Private. "
        "One short Group line only — no list of her kinks where he can steal the script.]"
    )
