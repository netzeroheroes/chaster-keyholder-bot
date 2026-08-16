"""Denial dossier: cage, last orgasm, seasonal Locktober — KH decides release."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from app.clock import local_now

_INTAKE = re.compile(
    r"\b("
    r"intake|"
    r"interview him|"
    r"ask (?:him )?(?:about )?(?:his )?(?:cage|cock|orgasm)|"
    r"get (?:his )?(?:details|dossier)|"
    r"how long (?:should|shall) (?:he|we) (?:stay )?lock"
    r")\b",
    re.I,
)

_LAST_ORGASM = re.compile(
    r"\b(?:last\s+)?(?:came|orgasm(?:ed)?|ejaculat(?:ed|ion)|cum(?:med)?)\b"
    r".{0,40}?"
    r"(?:"
    r"(?P<iso>\d{4}-\d{2}-\d{2})"
    r"|(?P<dmy>\d{1,2}\s+\w+\s+\d{4})"
    r"|(?P<ago>(?P<n>\d+)\s+(?P<unit>days?|weeks?|months?)\s+ago)"
    r"|(?P<yday>yesterday)"
    r")",
    re.I,
)

_CAGE = re.compile(
    r"\b("
    r"holy\s+trainer|htv\s*\d*|nub|nano|cobra|kink3d|"
    r"(?:steel|plastic|silicone|resin)\s+cage"
    r")\b",
    re.I,
)

_GOAL = re.compile(
    r"\b(?:lock(?:ed)?\s+(?:for|goal)|goal)\s+"
    r"(\d+)\s*(days?|weeks?|months?)\b",
    re.I,
)


def wants_intake(message: str) -> bool:
    return bool(_INTAKE.search(message or ""))


def _parse_date_fragment(m: re.Match[str], *, today: date) -> str | None:
    if m.group("iso"):
        return m.group("iso")
    if m.group("yday"):
        return (today - timedelta(days=1)).isoformat()
    if m.group("ago"):
        n = int(m.group("n"))
        unit = (m.group("unit") or "days").lower()
        if unit.startswith("week"):
            n *= 7
        elif unit.startswith("month"):
            n *= 30
        return (today - timedelta(days=n)).isoformat()
    if m.group("dmy"):
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(m.group("dmy"), fmt).date().isoformat()
            except ValueError:
                continue
    return None


def parse_denial_updates(message: str, *, today: date | None = None) -> dict[str, str]:
    """Pull cage / last orgasm / lock goal from a spoken line."""
    text = message or ""
    day = today or local_now().date()
    out: dict[str, str] = {}
    om = _LAST_ORGASM.search(text)
    if om:
        parsed = _parse_date_fragment(om, today=day)
        if parsed:
            out["last_orgasm"] = parsed
    cm = _CAGE.search(text)
    if cm:
        out["cage"] = cm.group(1).strip()
    gm = _GOAL.search(text)
    if gm:
        n = int(gm.group(1))
        unit = (gm.group(2) or "days").lower()
        if unit.startswith("week"):
            n *= 7
        elif unit.startswith("month"):
            n *= 30
        out["lock_goal_days"] = str(n)
    return out


def days_since_orgasm(chastity: dict[str, Any], *, today: date | None = None) -> int | None:
    raw = str((chastity or {}).get("last_orgasm") or "").strip()
    if not raw:
        return None
    try:
        then = date.fromisoformat(raw[:10])
    except ValueError:
        return None
    day = today or local_now().date()
    return max(0, (day - then).days)


def format_seasonal_block(*, today: date | None = None) -> str:
    day = today or local_now().date()
    if day.month == 10:
        return (
            "[SEASON — LOCKTOBER]\n"
            "It is October. Encourage staying locked the whole month. "
            "Do not offer unlock or orgasm unless the keyholder typed that this turn."
        )
    if day.month == 9:
        return (
            "[SEASON — September]\n"
            "Locktober is next month. Tease the idea of staying locked through October. "
            "She decides. Do not lock him into it yourself."
        )
    return ""


def format_denial_block(memory: Any, *, today: date | None = None) -> str:
    ch = dict(getattr(memory, "chastity", None) or {})
    day = today or local_now().date()
    denied = days_since_orgasm(ch, today=day)
    cage = (ch.get("cage") or "").strip() or "unknown"
    goal = (ch.get("lock_goal_days") or "").strip()
    lines = [
        "[DENIAL DOSSIER — tease with this; do not invent missing bits]",
        f"Cage: {cage}.",
    ]
    if denied is None:
        lines.append(
            "Last orgasm: unknown. If she wants a count, ask once — "
            "do not nag for the date (wall clock is in [CLOCK])."
        )
    else:
        lines.append(
            f"Last orgasm: {ch.get('last_orgasm')} ({denied} days denied). "
            "Tease the wait. Do not offer a cum from this number."
        )
    if goal:
        lines.append(f"Lock goal she set: {goal} days. Unlock is hers, never yours.")
    else:
        lines.append("No lock-goal days stored. She sets the period — you do not.")
    lines.append(
        "You are an AI in chat. No physical contact. "
        "Pic / porn / public-post tasks only if she ordered them this turn."
    )
    seasonal = format_seasonal_block(today=day)
    if seasonal:
        lines.append(seasonal)
    return "\n".join(lines)


def apply_denial_updates(memory: Any, updates: dict[str, str]) -> dict[str, str]:
    if not updates:
        return {}
    ch = dict(getattr(memory, "chastity", None) or {})
    ch.update(updates)
    memory.update_fields(chastity=ch)
    return updates


def intake_director(*, room: str) -> str:
    if room == "private":
        return (
            "[DIRECTOR: Intake. Ask HER what you still need: his cage, last orgasm, "
            "hard limits. Or say you'll ask him in Group if she wants him grilled. "
            "Do not decide his lock length. Suggest a period for her to accept.]"
        )
    return (
        "[DIRECTOR: Intake in Group. Ask him ONE thing this turn "
        "(cage, last orgasm, or a limit) — not a form. She is the keyholder.]"
    )
