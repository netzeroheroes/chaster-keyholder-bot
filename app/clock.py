"""Wall-clock time for the session timezone (not Chaster remaining)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

try:
    import tzdata  # noqa: F401  — IANA zones on Windows
except ImportError:
    pass

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[misc, assignment]

_CLOCK_ASK = re.compile(
    r"\b("
    r"what time is it|"
    r"what(?:'s| is) the (actual |current |real )?time|"
    r"(actual|current|real) time|"
    r"the time (now|here)|"
    r"time (now|here|in my|in our|in the)|"
    r"my timezone|"
    r"your timezone|"
    r"what(?:'s| is) the clock|"
    r"tell me the time|"
    r"do you know (the |what )?time|"
    r"time[- ]aware|"
    r"are you (time[- ]aware|aware of (the )?time)"
    r")\b",
    re.I,
)

_LOCK_TIME_ASK = re.compile(
    r"\b("
    r"how long (left|remaining)|"
    r"time left|"
    r"remaining time|"
    r"when (do|will) i (get out|unlock)|"
    r"how much (lock )?time|"
    r"lock time|"
    r"end date|"
    r"what(?:'s| is) his (?:lock )?time|"
    r"his time looking|"
    r"how(?:'s|s| is) (?:his |the )?(?:lock|timer)"
    r")\b",
    re.I,
)


def session_timezone() -> str:
    try:
        from app.runtime_controls import get_controls

        tz = (getattr(get_controls(), "autopilot_timezone", None) or "").strip()
        return tz or "Europe/London"
    except Exception:  # noqa: BLE001
        return "Europe/London"


def _tzinfo(name: str | None = None) -> Any:
    key = (name or session_timezone()).strip() or "Europe/London"
    if ZoneInfo is not None:
        try:
            return ZoneInfo(key)
        except Exception:  # noqa: BLE001
            pass
    return timezone.utc


def local_now(*, tz_name: str | None = None) -> datetime:
    tz = _tzinfo(tz_name)
    now = datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def format_local_now(*, tz_name: str | None = None) -> str:
    now = local_now(tz_name=tz_name)
    tz = tz_name or session_timezone()
    return f"{now.strftime('%A')} {now.day} {now.strftime('%B %Y, %H:%M')} {tz}"


def asks_clock_time(message: str) -> bool:
    return bool(_CLOCK_ASK.search(message or ""))


def asks_lock_remaining(message: str) -> bool:
    return bool(_LOCK_TIME_ASK.search(message or ""))


_COUNTDOWN_WATCH = re.compile(
    r"("
    r"\b(?:till|until|to)\s+(?:unlock|release|i(?:'m| am)\s+free)\b|"
    r"\btill (?:my )?(?:chastity )?timer\b|"
    r"\btimer runs out\b|"
    r"\bcountdown\b|"
    r"\b\d+\s*days?\b[^.!?\n]{0,40}\b(?:unlock|release)\b"
    r")",
    re.I,
)


def watching_unlock_countdown(message: str) -> bool:
    """True when he is treating remaining time as a scheduled unlock."""
    return bool(_COUNTDOWN_WATCH.search(message or ""))


def countdown_director() -> str:
    return (
        "[DIRECTOR: He is watching the unlock clock. Do not confirm his numbers. "
        "(I tap the cage.) Short spoken line. The timer is not his. "
        "A countdown is not an unlock. Do not offer a cum.]"
    )


def format_clock_block(*, tz_name: str | None = None) -> str:
    stamp = format_local_now(tz_name=tz_name)
    return (
        f"[CLOCK — wall clock, not lock remaining]\n"
        f"{stamp}\n"
        "If they ask what time it is / the actual time / timezone, answer with this. "
        "Hidden / remaining is the Chaster lock timer — do not mix them up."
    )


def format_clock_reply(*, role: str = "sub", tz_name: str | None = None) -> str:
    stamp = format_local_now(tz_name=tz_name)
    if role == "domme":
        return (
            f"Yes — I know the clock. It's {stamp}. "
            "That's the wall clock, not his lock remaining. "
            "Say when you want a hint dropped and I'll hold it until then."
        )
    return (
        f"It's {stamp}. That's the clock here — not how long you're locked."
    )
