from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, time, timezone
from typing import TYPE_CHECKING, Any

try:
    from zoneinfo import ZoneInfo
except Exception:  # noqa: BLE001
    ZoneInfo = None  # type: ignore[misc, assignment]

if TYPE_CHECKING:
    from app.agent import ChatAgent
    from app.bridge import GroupBridge
    from app.chaster import ChasterClient
    from app.config import Settings
    from app.memory import LongTermMemory
    from app.scene import SceneState
    from app.sessions import SessionStore

log = logging.getLogger(__name__)


def _parse_hhmm(value: str) -> time:
    raw = (value or "00:00").strip()
    parts = raw.split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    return time(hour=h % 24, minute=m % 60)


def _ctrl(settings: Settings):
    try:
        from app.runtime_controls import get_controls

        return get_controls()
    except Exception:  # noqa: BLE001
        return settings


def _tzinfo(name: str | None):
    key = (name or "UTC").strip() or "UTC"
    if ZoneInfo is not None:
        try:
            return ZoneInfo(key)
        except Exception:  # noqa: BLE001
            pass
    return timezone.utc


def window_open(settings: Settings, now: datetime | None = None) -> bool:
    """True if current local time is inside the configured daily window."""
    c = _ctrl(settings)
    tz = _tzinfo(getattr(c, "autopilot_timezone", None))
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    start = _parse_hhmm(getattr(c, "autopilot_window_start", "18:00"))
    end = _parse_hhmm(getattr(c, "autopilot_window_end", "23:00"))
    t = now.timetz().replace(tzinfo=None)
    if start <= end:
        return start <= t <= end
    # Overnight window (e.g. 22:00–02:00)
    return t >= start or t <= end


def in_window(settings: Settings, now: datetime | None = None) -> bool:
    """Enabled AND inside the daily window."""
    c = _ctrl(settings)
    if not getattr(c, "autopilot_enabled", False):
        return False
    return window_open(settings, now)


_LAST_TICK_ISO: str = ""
_NEXT_WAKE_ISO: str = ""
_LAST_SKIP_REASON: str = ""


def autopilot_status(settings: Settings) -> dict[str, Any]:
    """Live status for Domme settings UI / debugging."""
    c = _ctrl(settings)
    enabled = bool(getattr(c, "autopilot_enabled", False))
    open_now = window_open(settings)
    return {
        "autopilot_enabled": enabled,
        "in_window": bool(enabled and open_now),
        "window_open": open_now,
        "window_start": getattr(c, "autopilot_window_start", "18:00"),
        "window_end": getattr(c, "autopilot_window_end", "23:00"),
        "timezone": getattr(c, "autopilot_timezone", "Europe/London"),
        "min_gap_minutes": int(getattr(c, "autopilot_min_minutes", 45) or 45),
        "max_gap_minutes": int(getattr(c, "autopilot_max_minutes", 120) or 120),
        "allow_chaster": bool(getattr(c, "autopilot_allow_chaster", False)),
        "last_tick_at": _LAST_TICK_ISO or None,
        "next_wake_at": _NEXT_WAKE_ISO or None,
        "last_skip_reason": _LAST_SKIP_REASON or None,
    }


async def run_unprompted_tick(
    *,
    settings: Settings,
    agent: ChatAgent,
    store: SessionStore,
    scene: SceneState,
    memory: LongTermMemory,
    bridge: GroupBridge,
    chaster: ChasterClient | None,
) -> dict[str, Any] | None:
    """One spontaneous group tease; optionally a mild lock nudge."""
    from app.chaster_actions import run_chaster_intent, ChasterIntent
    from app.persist import save_sessions
    from app.roles import bot_label

    if not in_window(settings):
        return None

    bot = bot_label(memory)
    from app.roles import domme_address

    title = domme_address(memory)
    sub = memory.sub_name or "BOY"

    c = _ctrl(settings)
    chaster_line = ""
    if (
        chaster
        and chaster.configured
        and getattr(c, "autopilot_allow_chaster", False)
        and random.random()
        < max(0.0, min(1.0, float(getattr(c, "autopilot_chaster_chance", 0.35))))
    ):
        # Chaster is the main lever — prefer real lock detriment
        action = random.choice(["add_time", "add_time", "freeze", "hide_time"])
        if action == "add_time":
            secs = int(getattr(c, "autopilot_punish_seconds", None) or 600)
            intent = ChasterIntent(kind="add_time", seconds=max(60, secs))
        elif action == "freeze":
            intent = ChasterIntent(kind="freeze")
        else:
            intent = ChasterIntent(kind="hide_time")
        result = await run_chaster_intent(
            chaster, intent, requested_by=f"{bot} (autopilot)"
        )
        if result.ok and not result.blocked:
            chaster_line = (
                f"\n[LOCK CHANGE CONFIRMED: {intent.kind}. "
                f"Remaining={((result.lock or {}).get('remaining'))}, "
                f"frozen={((result.lock or {}).get('is_frozen'))}]"
            )
        else:
            chaster_line = "\n[LOCK CHANGE skipped/failed — do not invent one.]"

    system = (
        f"You are {bot}, the AI Domme/keyholder. Unprompted check-in in GROUP chat.\n"
        f"Human Domme is {title}. Sub is {sub}.\n"
        "Write ONE short cruel-playful line to the Sub (2-4 sentences).\n"
        "Do not claim lock changes unless LOCK CHANGE CONFIRMED is present.\n"
        "Never involve anyone under 18."
    )
    user = (
        "Send an unprompted tease/order while the Sub is under our control."
        + chaster_line
    )
    try:
        text, _ = await agent.reply(user, history=[], system_prompt=system)
    except Exception:
        log.exception("Autopilot LLM failed")
        return None

    text = (text or "").strip()
    if not text:
        return None
    await bridge.publish_group_messages(store, [text], speaker=bot)
    save_sessions(store)
    log.info("Autopilot posted unprompted group line")
    return {"posted": text}


async def autopilot_loop(
    *,
    settings: Settings,
    agent: ChatAgent,
    store: SessionStore,
    scene: SceneState,
    memory: LongTermMemory,
    bridge: GroupBridge,
    chaster: ChasterClient | None,
) -> None:
    global _LAST_TICK_ISO, _NEXT_WAKE_ISO, _LAST_SKIP_REASON
    c0 = _ctrl(settings)
    log.info(
        "Autopilot loop started enabled=%s window=%s-%s tz=%s",
        getattr(c0, "autopilot_enabled", False),
        getattr(c0, "autopilot_window_start", "?"),
        getattr(c0, "autopilot_window_end", "?"),
        getattr(c0, "autopilot_timezone", "?"),
    )
    while True:
        try:
            c = _ctrl(settings)
            enabled = bool(getattr(c, "autopilot_enabled", False))
            open_now = window_open(settings)
            if enabled and open_now:
                _LAST_SKIP_REASON = ""
                posted = await run_unprompted_tick(
                    settings=settings,
                    agent=agent,
                    store=store,
                    scene=scene,
                    memory=memory,
                    bridge=bridge,
                    chaster=chaster,
                )
                if posted:
                    _LAST_TICK_ISO = datetime.now(
                        _tzinfo(getattr(c, "autopilot_timezone", None))
                    ).isoformat(timespec="seconds")
                lo = max(1, int(getattr(c, "autopilot_min_minutes", 45)))
                hi = max(lo, int(getattr(c, "autopilot_max_minutes", 120)))
                delay = random.randint(lo, hi) * 60
            else:
                if not enabled:
                    _LAST_SKIP_REASON = "autopilot_enabled is false on server"
                else:
                    _LAST_SKIP_REASON = (
                        f"outside window "
                        f"{getattr(c, 'autopilot_window_start', '?')}-"
                        f"{getattr(c, 'autopilot_window_end', '?')} "
                        f"{getattr(c, 'autopilot_timezone', '?')}"
                    )
                delay = 30  # pick up settings changes quickly
            tz = _tzinfo(getattr(c, "autopilot_timezone", None))
            _NEXT_WAKE_ISO = (
                datetime.now(tz) + timedelta(seconds=delay)
            ).isoformat(timespec="seconds")
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Autopilot tick failed")
            _LAST_SKIP_REASON = "tick error — see server logs"
            await asyncio.sleep(60)
