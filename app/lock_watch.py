"""Watch Chaster lock history and let the AI Domme react in group chat."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.bot_actions import is_bot_extension_history_event
from app.persist import save_sessions
from app.roles import bot_label, session_id_for
from app.sessions import DisplayMessage

if TYPE_CHECKING:
    from app.agent import ChatAgent
    from app.chaster import ChasterClient
    from app.config import Settings
    from app.memory import LongTermMemory
    from app.scene import SceneState
    from app.sessions import SessionStore

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATE_PATH = DATA_DIR / "lock_watch.json"

# Games / other plugins — always worth a group reaction
_REACT_TYPES = frozenset(
    {
        "pillory_started",
        "pillory_ended",
        "temporary_opening_opened",
        "temporary_opening_locked",
        "combination_verified",
        "extension_enabled",
        "extension_disabled",
        "extension_updated",
        "task_completed",
        "task_failed",
        "dice_rolled",
        "wheel_of_fortune_turned",
        "link_submitted",
        "share_link",
        "custom",
        "unlocked",
        "locked",
        "max_limit_date_removed",
        "session_offer_accepted",
    }
)

# Timer edits from Duo Domme are already confirmed in chat — skip those.
# Same event types from the human keyholder (manual on Chaster) SHOULD react.
_SELF_EXTENSIONS = frozenset({"duo-domme"})
_TIMER_TYPES = frozenset(
    {
        "time_changed",
        "lock_frozen",
        "lock_unfrozen",
        "timer_hidden",
        "timer_revealed",
    }
)


def _is_our_duo_domme_action(event: dict[str, Any]) -> bool:
    ext = str(event.get("extension") or "").strip().lower()
    role = str(event.get("role") or "").strip().lower()
    return ext in _SELF_EXTENSIONS or (
        role == "extension" and ext in _SELF_EXTENSIONS
    )


def _is_our_bot_action(event: dict[str, Any]) -> bool:
    """Duo Domme session actions, or keyholder-token API edits we just made."""
    if _is_our_duo_domme_action(event):
        return True
    return is_bot_extension_history_event(event)


def _should_react(event: dict[str, Any]) -> bool:
    etype = str(event.get("type") or "")
    # Our own edits are already narrated in chat — don't double-claim as Mistress.
    if _is_our_bot_action(event):
        return False
    if etype in _TIMER_TYPES:
        return True
    if etype in _REACT_TYPES:
        return True
    if etype.endswith("_changed"):
        return True
    # Unknown plugin events
    return bool(event.get("extension"))


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"last_id": "", "seen": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"last_id": "", "seen": []}


def _save_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def format_history_event(event: dict[str, Any]) -> str:
    """Human-readable one-liner for a lock history entry."""
    etype = str(event.get("type") or "event")
    ext = str(event.get("extension") or "").strip()
    role = str(event.get("role") or "").strip().lower()
    bot_edit = _is_our_bot_action(event)
    if bot_edit:
        who = "Duo Domme (bot)"
    elif role == "keyholder":
        who = "Mistress (keyholder, manual on Chaster)"
    elif ext.lower() in _SELF_EXTENSIONS or role == "extension":
        who = "Duo Domme (bot)" if ext.lower() in _SELF_EXTENSIONS else (ext or "an extension")
    elif role == "wearer":
        who = "the Sub (wearer)"
    else:
        who = "Someone"
    title = str(event.get("title") or "").replace("%USER%", who)
    desc = str(event.get("description") or "").strip()
    bits = [title or etype]
    if desc:
        bits.append(desc)
    if bot_edit:
        bits.append("(bot via API — Chaster logs this as keyholder)")
    elif role == "keyholder":
        bits.append("(manual keyholder action — not the bot)")
    elif ext:
        bits.append(f"(plugin: {ext})")
    return " — ".join(bits)


def mark_history_events_seen(events: list[dict[str, Any]]) -> None:
    """Record history ids so the poller does not double-handle webhook events."""
    if not events:
        return
    state = _load_state()
    seen = [str(x) for x in (state.get("seen") or []) if x]
    seen_set = set(seen)
    last_id = str(state.get("last_id") or "")
    for ev in events:
        eid = str(ev.get("_id") or "")
        if not eid:
            continue
        if eid not in seen_set:
            seen.append(eid)
            seen_set.add(eid)
        # Mongo ObjectIds sort chronologically as strings
        if not last_id or eid > last_id:
            last_id = eid
    state["seen"] = seen[-80:]
    if last_id:
        state["last_id"] = last_id
    _save_state(state)


async def fetch_new_events(
    chaster: ChasterClient, *, limit: int = 15
) -> list[dict[str, Any]]:
    """Return newest unseen history events (oldest→newest). Seeds on first run."""
    lock_id = (chaster.settings.chaster_lock_id or "").strip()
    if not lock_id:
        st = await chaster.status()
        lock_id = str((st.get("lock") or {}).get("lock_id") or "")
    if not lock_id:
        return []

    results = await chaster.get_lock_history(lock_id, limit=limit)
    if not results:
        return []

    state = _load_state()
    last_id = str(state.get("last_id") or "")
    seen_set = {str(x) for x in (state.get("seen") or []) if x}
    newest_id = str(results[0].get("_id") or "")

    if not last_id:
        # First run: remember tip of history, don't flood chat
        state["last_id"] = newest_id
        state["seen"] = [newest_id]
        _save_state(state)
        return []

    new: list[dict[str, Any]] = []
    for ev in results:
        eid = str(ev.get("_id") or "")
        if not eid or eid == last_id:
            break
        if eid in seen_set:
            # Already handled via webhook — advance watermark past it
            continue
        new.append(ev)

    if not new:
        # Still advance tip so we don't re-scan forever after webhook-only updates
        if newest_id and newest_id != last_id:
            state["last_id"] = newest_id
            if newest_id not in seen_set:
                seen = list(state.get("seen") or [])
                seen.append(newest_id)
                state["seen"] = seen[-80:]
            _save_state(state)
        return []

    # results are newest-first; react oldest-first
    new.reverse()
    state["last_id"] = newest_id
    seen = list(state.get("seen") or [])
    for ev in new:
        eid = str(ev.get("_id") or "")
        if eid and eid not in seen_set:
            seen.append(eid)
            seen_set.add(eid)
    state["seen"] = seen[-80:]
    _save_state(state)
    return new


async def react_to_lock_events(
    *,
    agent: ChatAgent,
    store: SessionStore,
    scene: SceneState,
    memory: LongTermMemory,
    chaster: ChasterClient,
    events: list[dict[str, Any]],
    rad: Any | None = None,
) -> int:
    """Post AI Domme reactions into the group room for new lock history events."""
    if not events:
        return 0

    # Physical lockbox bridge — no AI, just API sync (time from Chaster)
    if rad is not None:
        try:
            from app.lockbox_sync import handle_chaster_events

            await handle_chaster_events(rad, events, chaster=chaster)
        except Exception:  # noqa: BLE001
            log.exception("R+D lockbox sync from Chaster events failed")

    bot = bot_label(memory)
    from app.roles import domme_address

    title = domme_address(memory)
    reacted = 0
    for ev in events[:5]:
        if not _should_react(ev):
            continue
        etype = str(ev.get("type") or "")
        role = str(ev.get("role") or "").strip().lower()
        summary = format_history_event(ev)
        # Only true manual Mistress clicks — not bot API edits logged as keyholder.
        manual = role == "keyholder" and not _is_our_bot_action(ev)
        system = (
            f"You are {bot}, the AI Domme/keyholder in GROUP chat (18+).\n"
            f"ACTIVE CHANNEL: GROUP — Domme + Sub + you can all see this.\n"
            f"A real Chaster lock event just happened. React in 1–3 short sentences "
            f"to the Sub (and {title} if relevant). Stay in character. "
            f"Do NOT invent further lock changes. Do NOT emit [[[LOCK]]] tags.\n"
            f"IMPORTANT: In Chaster, 'extension' means a lock PLUGIN (wheel, tasks, "
            f"puzzle, etc.), NOT 'more lock time'. Never congratulate someone for "
            f"'an extension' unless a plugin was actually enabled/updated.\n"
        )
        if manual:
            system += (
                f"{title} just changed the lock MANUALLY on Chaster (not via chat / "
                f"not Duo Domme). Acknowledge her action — e.g. she added/removed time "
                f"— and tease the Sub about it. Do not claim YOU did it.\n"
            )
        system += (
            f"Event: {summary}\n"
            f"Raw type={etype} role={role} extension/plugin={ev.get('extension')} "
            f"payload={json.dumps(ev.get('payload') or {}, ensure_ascii=False)[:300]}"
        )
        try:
            reply, _ = await agent.reply(
                f"[LOCK EVENT] {summary}",
                history=[],
                system_prompt=system,
            )
        except Exception:  # noqa: BLE001
            log.exception("Lock-watch LLM reaction failed")
            reply = f"Something just happened on your lock: {summary}"
        text = (reply or "").strip() or f"Noted on your lock: {summary}"
        # Strip accidental LOCK tags from reactions
        from app.chaster_actions import extract_lock_commands

        text, _ = extract_lock_commands(text)
        store.append_display(
            DisplayMessage(speaker=bot, content=text, room="group")
        )
        # Keep model history loosely aware
        sid = session_id_for("group")
        store.append(
            sid,
            {"role": "assistant", "content": text},
        )
        reacted += 1
        log.info("Lock-watch reacted to %s: %s", etype, summary[:120])
    if reacted:
        save_sessions(store)
    return reacted


async def lock_watch_loop(
    *,
    settings: Settings,
    agent: ChatAgent,
    store: SessionStore,
    scene: SceneState,
    memory: LongTermMemory,
    chaster: ChasterClient,
    rad: Any | None = None,
) -> None:
    """Background poll of Chaster lock history + periodic R+D timer sync."""
    interval = max(15, int(getattr(settings, "lock_watch_seconds", 45) or 45))
    timer_every = max(
        15, int(getattr(settings, "rad_timer_sync_seconds", 60) or 60)
    )
    last_timer_sync = 0.0
    while True:
        try:
            if (
                getattr(settings, "lock_watch_enabled", True)
                and chaster.configured
            ):
                events = await fetch_new_events(chaster)
                if events:
                    await react_to_lock_events(
                        agent=agent,
                        store=store,
                        scene=scene,
                        memory=memory,
                        chaster=chaster,
                        events=events,
                        rad=rad,
                    )
                # Flag edges (freeze/hide/unfreeze/reveal) + hold placeholders.
                # Periodic remaining-time sync keeps R+D aligned with Chaster.
                if rad is not None:
                    try:
                        from app.lockbox_sync import (
                            maybe_resync_after_chaster_flags,
                            sync_duration_from_chaster,
                        )

                        await maybe_resync_after_chaster_flags(rad, chaster)
                        now = asyncio.get_event_loop().time()
                        if not getattr(settings, "rad_manual_only", False):
                            if now - last_timer_sync >= timer_every:
                                await sync_duration_from_chaster(
                                    rad, chaster, reason="periodic"
                                )
                                last_timer_sync = now
                    except Exception:  # noqa: BLE001
                        log.debug("Periodic R+D duration sync skipped", exc_info=True)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Lock-watch tick failed")
        await asyncio.sleep(interval)
