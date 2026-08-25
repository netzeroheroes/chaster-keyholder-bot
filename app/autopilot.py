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

_FALLBACK_TEASES = (
    "{sub} — just us. Stay caged. I'll talk to {title} about what you get next.",
    "Checking in, {sub}. Hands off. You're still mine until {title} says otherwise.",
    "Don't get comfortable, {sub}. I'm watching the lock — and you.",
    "Quiet stretch for you, {sub}. Behave. I'll decide when you get attention.",
    "Still locked. Still owned. Say thank you in your head, {sub}.",
)


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
_FORCE_EVENT: asyncio.Event | None = None
_LOOP_STARTED: bool = False


def _force_event() -> asyncio.Event:
    global _FORCE_EVENT
    if _FORCE_EVENT is None:
        _FORCE_EVENT = asyncio.Event()
    return _FORCE_EVENT


def request_force_tick() -> None:
    """Wake the loop and run a tease as soon as possible (Domme 'Tease now')."""
    _force_event().set()


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
        "loop_running": _LOOP_STARTED,
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
    force: bool = False,
) -> dict[str, Any] | None:
    """One spontaneous group tease; optionally a mild lock nudge."""
    global _LAST_SKIP_REASON, _LAST_TICK_ISO

    from app.chaster_actions import run_chaster_intent, ChasterIntent
    from app.persist import save_sessions
    from app.roles import bot_label, domme_address

    if not force and not in_window(settings):
        return None

    bot = bot_label(memory)
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
        from app.runtime_controls import bot_lock_action_allowed

        pool: list[str] = []
        if bot_lock_action_allowed("add_time", seconds=60):
            pool.extend(["add_time", "add_time"])
        if bot_lock_action_allowed("freeze"):
            pool.append("freeze")
        if bot_lock_action_allowed("hide_time"):
            pool.append("hide_time")
        action = random.choice(pool) if pool else ""
        intent = None
        if action == "add_time":
            secs = int(getattr(c, "autopilot_punish_seconds", None) or 600)
            intent = ChasterIntent(kind="add_time", seconds=max(60, secs))
        elif action == "freeze":
            intent = ChasterIntent(kind="freeze")
        elif action == "hide_time":
            intent = ChasterIntent(kind="hide_time")
        result = None
        if intent is not None:
            try:
                result = await asyncio.wait_for(
                    run_chaster_intent(
                        chaster, intent, requested_by=f"{bot} (autopilot)"
                    ),
                    timeout=20.0,
                )
            except asyncio.TimeoutError:
                log.warning("Autopilot Chaster nudge timed out (%s)", intent.kind)
                chaster_line = "\n[LOCK CHANGE skipped/failed — do not invent one.]"
                result = None
            except Exception:  # noqa: BLE001
                log.exception("Autopilot Chaster nudge failed")
                chaster_line = "\n[LOCK CHANGE skipped/failed — do not invent one.]"
                result = None
        if result is not None:
            if result.ok and not result.blocked:
                chaster_line = (
                    f"\n[LOCK CHANGE CONFIRMED: {intent.kind}. "
                    f"Remaining={((result.lock or {}).get('remaining'))}, "
                    f"frozen={((result.lock or {}).get('is_frozen'))}]"
                )
            else:
                chaster_line = "\n[LOCK CHANGE skipped/failed — do not invent one.]"

    from app.bot_persona import format_persona_block

    system = (
        f"You are {bot}, helping the keyholder. Unprompted check-in in GROUP chat.\n"
        f"Keyholder is {title}. Lockee is {sub}. Speak to him only.\n"
        "Write ONE short taunt about the cage and the wait. "
        "No (stage directions). No instruction brackets. Do not offer unlock.\n"
        "Do not invent how long since you last spoke, whether he obeyed, or remaining time "
        "unless LOCK CHANGE CONFIRMED is present.\n"
        "Never involve anyone under 18.\n"
        + format_persona_block(room="group")
    )
    user = (
        "Send an unprompted tease/order while the Sub is under our control."
        + chaster_line
    )
    text = ""
    try:
        raw, _ = await asyncio.wait_for(
            agent.reply(user, history=[], system_prompt=system),
            timeout=60.0,
        )
        text = (raw or "").strip()
        if text in ("(empty response)",):
            text = ""
    except asyncio.TimeoutError:
        log.warning("Autopilot LLM timed out — using fallback tease")
        _LAST_SKIP_REASON = "LLM timed out — posted fallback"
    except Exception:
        log.exception("Autopilot LLM failed — using fallback tease")
        _LAST_SKIP_REASON = "LLM failed — posted fallback"

    if not text:
        text = random.choice(_FALLBACK_TEASES).format(sub=sub, title=title)
        if not _LAST_SKIP_REASON:
            _LAST_SKIP_REASON = "empty LLM — posted fallback"

    await bridge.publish_group_messages(store, [text], speaker=bot)
    try:
        save_sessions(store)
    except Exception:  # noqa: BLE001
        log.exception("Autopilot save_sessions failed (message still in memory)")
    c_tz = _tzinfo(getattr(c, "autopilot_timezone", None))
    _LAST_TICK_ISO = datetime.now(c_tz).isoformat(timespec="seconds")
    log.info("Autopilot posted unprompted group line (%s chars)", len(text))
    return {"posted": text}


async def _sleep_interruptible(total_seconds: float) -> bool:
    """Sleep in short chunks. Returns True if a force-tick was requested."""
    ev = _force_event()
    remaining = max(0.0, float(total_seconds))
    chunk = 15.0
    while remaining > 0:
        if ev.is_set():
            return True
        wait = min(chunk, remaining)
        try:
            await asyncio.wait_for(ev.wait(), timeout=wait)
            return True
        except asyncio.TimeoutError:
            remaining -= wait
    return ev.is_set()


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
    global _LAST_TICK_ISO, _NEXT_WAKE_ISO, _LAST_SKIP_REASON, _LOOP_STARTED
    _LOOP_STARTED = True
    ev = _force_event()
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
            forced = ev.is_set()
            if forced:
                ev.clear()

            should_tick = forced or (enabled and open_now)
            if should_tick:
                if not forced:
                    _LAST_SKIP_REASON = ""
                posted = await run_unprompted_tick(
                    settings=settings,
                    agent=agent,
                    store=store,
                    scene=scene,
                    memory=memory,
                    bridge=bridge,
                    chaster=chaster,
                    force=forced,
                )
                if posted:
                    if "fallback" not in (_LAST_SKIP_REASON or ""):
                        _LAST_SKIP_REASON = ""
                elif forced:
                    _LAST_SKIP_REASON = "forced tick produced no message"
                lo = max(1, int(getattr(c, "autopilot_min_minutes", 45)))
                hi = max(lo, int(getattr(c, "autopilot_max_minutes", 120)))
                # After a forced tease, still respect the gap unless disabled
                delay = random.randint(lo, hi) * 60 if enabled else 30
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
            await _sleep_interruptible(delay)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Autopilot tick failed")
            _LAST_SKIP_REASON = "tick error — see server logs"
            await _sleep_interruptible(60)
