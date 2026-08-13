from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, time
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

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


def in_window(settings: Settings, now: datetime | None = None) -> bool:
    c = _ctrl(settings)
    if not getattr(c, "autopilot_enabled", False):
        return False
    try:
        tz = ZoneInfo(getattr(c, "autopilot_timezone", None) or "UTC")
    except Exception:  # noqa: BLE001
        tz = ZoneInfo("UTC")
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
            if getattr(c, "autopilot_enabled", False) and in_window(settings):
                await run_unprompted_tick(
                    settings=settings,
                    agent=agent,
                    store=store,
                    scene=scene,
                    memory=memory,
                    bridge=bridge,
                    chaster=chaster,
                )
                lo = max(1, int(getattr(c, "autopilot_min_minutes", 45)))
                hi = max(lo, int(getattr(c, "autopilot_max_minutes", 120)))
                delay = random.randint(lo, hi) * 60
            else:
                delay = 60  # re-check window every minute
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Autopilot tick failed")
            await asyncio.sleep(60)
