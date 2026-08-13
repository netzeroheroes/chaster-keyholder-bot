"""Chaster → Research & Desire Lockbox sync (no AI).

Chaster is the time source of truth. R+D templates are only used to *start*
a lock session; duration is immediately overwritten from Chaster remaining time.

- Hygiene open  → unlock physical box
- Hygiene close → re-lock box, duration = Chaster remaining
- time_changed / timer ticks → PATCH R+D duration to match Chaster
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.rad_lockbox import RadLockboxClient

if TYPE_CHECKING:
    from app.chaster import ChasterClient

log = logging.getLogger(__name__)

# R+D firmware allows ~30s .. years; keep a sane floor for API calls
_MIN_DURATION = 60
_MAX_DURATION = 86400 * 365 * 10  # 10 years

_LAST: dict[str, Any] = {
    "action": None,
    "ok": None,
    "detail": None,
    "at": None,
    "chaster_type": None,
    "chaster_remaining": None,
}


def last_sync_status() -> dict[str, Any]:
    return dict(_LAST)


def _stamp(
    *,
    action: str,
    ok: bool,
    detail: str,
    chaster_type: str | None = None,
    chaster_remaining: int | None = None,
) -> dict[str, Any]:
    _LAST.update(
        {
            "action": action,
            "ok": ok,
            "detail": detail,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "chaster_type": chaster_type,
            "chaster_remaining": chaster_remaining,
        }
    )
    return dict(_LAST)


def _sync_on(rad: RadLockboxClient) -> bool:
    return bool(
        rad.configured
        and getattr(rad.settings, "rad_lockbox_sync_enabled", False)
    )


def _clamp_duration(seconds: int) -> int:
    return max(_MIN_DURATION, min(_MAX_DURATION, int(seconds)))


async def chaster_remaining_seconds(chaster: ChasterClient | None) -> int | None:
    """Seconds left on the configured / first linked Chaster lock."""
    if chaster is None or not getattr(chaster, "configured", False):
        return None
    try:
        lock_id = (getattr(chaster.settings, "chaster_lock_id", None) or "").strip()
        lock = await chaster.get_lock(lock_id) if lock_id else None
        if not lock:
            sessions = await chaster.search_extension_sessions()
            if sessions:
                raw = sessions[0].get("lock") if isinstance(sessions[0], dict) else None
                if isinstance(raw, dict) and (raw.get("_id") or raw.get("id")):
                    lock = await chaster.get_lock(str(raw.get("_id") or raw.get("id"))) or raw
        if not isinstance(lock, dict):
            return None
        status = str(lock.get("status") or "").lower()
        if status in ("unlocked", "archived", "deserted", "ended"):
            return None
        end = lock.get("endDate")
        if not end:
            # Frozen / hidden / no end — keep a long placeholder so the box stays shut
            if lock.get("isFrozen"):
                return _MAX_DURATION
            return None
        end_dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        rem = int((end_dt - datetime.now(timezone.utc)).total_seconds())
        return rem if rem > 0 else None
    except Exception:  # noqa: BLE001
        log.exception("Failed to read Chaster remaining time")
        return None


async def ensure_template_id(rad: RadLockboxClient) -> int | None:
    """Use configured template, or auto-pick the first available (no dashboard UI needed)."""
    if rad.lock_settings_id is not None:
        return rad.lock_settings_id
    try:
        templates = await rad.list_templates()
    except Exception:  # noqa: BLE001
        log.exception("Could not list R+D templates")
        return None
    if not templates:
        return None
    # Prefer a template owned by the target lockee if known
    tid = rad.target_user_id
    owned = [t for t in templates if tid and t.get("ownerId") == tid]
    pick = owned[0] if owned else templates[0]
    lid = pick.get("id")
    try:
        return int(lid)
    except (TypeError, ValueError):
        return None


async def sync_duration_from_chaster(
    rad: RadLockboxClient,
    chaster: ChasterClient | None,
    *,
    reason: str = "time_sync",
    force: bool = False,
) -> dict[str, Any]:
    """PATCH active R+D session duration to match Chaster remaining time."""
    if not rad.configured:
        return _stamp(
            action="set_duration",
            ok=False,
            detail="RAD_API_TOKEN not set",
            chaster_type=reason,
        )
    if not force and not _sync_on(rad):
        return _stamp(
            action="set_duration",
            ok=False,
            detail="R+D sync disabled",
            chaster_type=reason,
        )
    rem = await chaster_remaining_seconds(chaster)
    if rem is None:
        return _stamp(
            action="set_duration",
            ok=False,
            detail="No Chaster remaining time available",
            chaster_type=reason,
        )
    duration = _clamp_duration(rem)
    try:
        session = await rad.get_active_session()
        if not session or not session.get("isActive"):
            return _stamp(
                action="set_duration",
                ok=False,
                detail="No active R+D session to update",
                chaster_type=reason,
                chaster_remaining=rem,
            )
        state = str(session.get("lockState") or "").lower()
        if state != "locked":
            return _stamp(
                action="set_duration",
                ok=False,
                detail=f"R+D session state is {state or '?'}, not locked",
                chaster_type=reason,
                chaster_remaining=rem,
            )
        current = session.get("duration")
        try:
            if current is not None and abs(int(current) - duration) < 30:
                return _stamp(
                    action="set_duration",
                    ok=True,
                    detail=f"Already ≈ Chaster ({duration}s)",
                    chaster_type=reason,
                    chaster_remaining=rem,
                )
        except (TypeError, ValueError):
            pass
        await rad.set_duration(duration)
        log.info(
            "R+D duration set to %ss from Chaster (%s)", duration, reason
        )
        return _stamp(
            action="set_duration",
            ok=True,
            detail=f"Set R+D duration to {duration}s from Chaster",
            chaster_type=reason,
            chaster_remaining=rem,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("R+D duration sync failed")
        return _stamp(
            action="set_duration",
            ok=False,
            detail=str(exc),
            chaster_type=reason,
            chaster_remaining=rem,
        )


async def unlock_for_hygiene(
    rad: RadLockboxClient,
    *,
    reason: str = "hygiene",
    force: bool = False,
) -> dict[str, Any]:
    if not rad.configured:
        return _stamp(
            action="unlock",
            ok=False,
            detail="RAD_API_TOKEN not set",
            chaster_type=reason,
        )
    if not force and not _sync_on(rad):
        return _stamp(
            action="unlock",
            ok=False,
            detail="R+D sync disabled (RAD_LOCKBOX_SYNC_ENABLED=false)",
            chaster_type=reason,
        )
    try:
        session = await rad.get_active_session()
        state = str((session or {}).get("lockState") or "").lower()
        if not session or not (session.get("isActive")):
            return _stamp(
                action="unlock",
                ok=True,
                detail="No active R+D session — already open",
                chaster_type=reason,
            )
        if state in ("completed", "abandoned"):
            return _stamp(
                action="unlock",
                ok=True,
                detail=f"R+D session already {state}",
                chaster_type=reason,
            )
        await rad.unlock()
        log.info("R+D lockbox unlocked for %s", reason)
        return _stamp(
            action="unlock",
            ok=True,
            detail="Unlocked R+D lockbox",
            chaster_type=reason,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("R+D unlock for %s failed", reason)
        return _stamp(
            action="unlock",
            ok=False,
            detail=str(exc),
            chaster_type=reason,
        )


async def relock_from_chaster(
    rad: RadLockboxClient,
    chaster: ChasterClient | None,
    *,
    reason: str = "hygiene_closed",
    force: bool = False,
) -> dict[str, Any]:
    """Start (or refresh) R+D lock and set duration from Chaster remaining."""
    if not rad.configured:
        return _stamp(
            action="lock",
            ok=False,
            detail="RAD_API_TOKEN not set",
            chaster_type=reason,
        )
    if not force and not _sync_on(rad):
        return _stamp(
            action="lock",
            ok=False,
            detail="R+D sync disabled (RAD_LOCKBOX_SYNC_ENABLED=false)",
            chaster_type=reason,
        )

    rem = await chaster_remaining_seconds(chaster)
    duration = _clamp_duration(rem) if rem is not None else None

    template_id = await ensure_template_id(rad)
    if template_id is None:
        return _stamp(
            action="lock",
            ok=False,
            detail="No R+D lock template available (API still needs one to start a session)",
            chaster_type=reason,
            chaster_remaining=rem,
        )

    try:
        session = await rad.get_active_session()
        if session and session.get("isActive"):
            state = str(session.get("lockState") or "").lower()
            if state == "locked":
                # Already locked — just push Chaster time
                if duration is not None:
                    await rad.set_duration(duration)
                    return _stamp(
                        action="lock",
                        ok=True,
                        detail=f"Already locked — duration synced to {duration}s from Chaster",
                        chaster_type=reason,
                        chaster_remaining=rem,
                    )
                return _stamp(
                    action="lock",
                    ok=True,
                    detail="R+D already locked (no Chaster time to sync)",
                    chaster_type=reason,
                    chaster_remaining=rem,
                )
            try:
                await rad.unlock()
            except Exception:  # noqa: BLE001
                pass

        await rad.lock(lock_settings_id=template_id)
        if duration is not None:
            try:
                await rad.set_duration(duration)
            except Exception as exc:  # noqa: BLE001
                log.exception("Locked but failed to set Chaster duration")
                return _stamp(
                    action="lock",
                    ok=False,
                    detail=f"Locked with template, but duration sync failed: {exc}",
                    chaster_type=reason,
                    chaster_remaining=rem,
                )
            detail = f"Re-locked; duration {duration}s from Chaster"
        else:
            detail = (
                "Re-locked with template duration "
                "(Chaster remaining unavailable — check CHASTER_LOCK_ID)"
            )
        log.info("R+D lockbox re-locked after %s (%s)", reason, detail)
        return _stamp(
            action="lock",
            ok=True,
            detail=detail,
            chaster_type=reason,
            chaster_remaining=rem,
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        # Lock call may error even when a session was created — recover.
        try:
            session = await rad.get_active_session()
        except Exception:  # noqa: BLE001
            session = None
        if session and session.get("isActive") and duration is not None:
            try:
                await rad.set_duration(duration)
                return _stamp(
                    action="lock",
                    ok=True,
                    detail=(
                        f"Session active after lock quirk; duration synced to "
                        f"{duration}s from Chaster"
                    ),
                    chaster_type=reason,
                    chaster_remaining=rem,
                )
            except Exception as exc2:  # noqa: BLE001
                msg = f"{msg} | duration sync: {exc2}"
        if "already have an active lock" in msg.lower() and duration is not None:
            try:
                await rad.set_duration(duration)
                return _stamp(
                    action="lock",
                    ok=True,
                    detail=f"Active session kept; duration synced to {duration}s from Chaster",
                    chaster_type=reason,
                    chaster_remaining=rem,
                )
            except Exception as exc2:  # noqa: BLE001
                return _stamp(
                    action="lock",
                    ok=False,
                    detail=(
                        f"Active lock exists but duration sync failed: {exc2}. "
                        "Use RAD_IS_TEST_LOCK=true if there is no R+D keyholder."
                    ),
                    chaster_type=reason,
                    chaster_remaining=rem,
                )
        log.exception("R+D re-lock after %s failed", reason)
        return _stamp(
            action="lock",
            ok=False,
            detail=msg,
            chaster_type=reason,
            chaster_remaining=rem,
        )


# Back-compat alias used by API routes
async def relock_after_hygiene(
    rad: RadLockboxClient,
    chaster: ChasterClient | None = None,
    *,
    reason: str = "hygiene_closed",
    force: bool = False,
) -> dict[str, Any]:
    return await relock_from_chaster(
        rad, chaster, reason=reason, force=force
    )


_TIME_SYNC_TYPES = frozenset(
    {
        "time_changed",
        "lock_frozen",
        "lock_unfrozen",
        "timer_hidden",
        "timer_revealed",
        "temporary_opening_locked",
        "locked",
    }
)


async def handle_chaster_events(
    rad: RadLockboxClient,
    events: list[dict[str, Any]],
    *,
    chaster: ChasterClient | None = None,
) -> list[dict[str, Any]]:
    """Mirror relevant Chaster history events onto the R+D lockbox."""
    if not events or not _sync_on(rad):
        return []

    hygiene = bool(getattr(rad.settings, "rad_sync_hygiene", True))
    session_sync = bool(getattr(rad.settings, "rad_sync_session_lock", False))
    results: list[dict[str, Any]] = []
    synced_time = False

    for ev in events:
        etype = str(ev.get("type") or "")
        if hygiene and etype == "temporary_opening_opened":
            results.append(await unlock_for_hygiene(rad, reason=etype))
        elif hygiene and etype == "temporary_opening_locked":
            results.append(
                await relock_from_chaster(rad, chaster, reason=etype)
            )
            synced_time = True
        elif session_sync and etype == "unlocked":
            results.append(await unlock_for_hygiene(rad, reason=etype))
        elif session_sync and etype == "locked":
            results.append(
                await relock_from_chaster(rad, chaster, reason=etype)
            )
            synced_time = True
        elif etype in _TIME_SYNC_TYPES and not synced_time:
            results.append(
                await sync_duration_from_chaster(rad, chaster, reason=etype)
            )
            synced_time = True

    return results
