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

# R+D firmware allows ~30s .. API max 10 years
_MIN_DURATION = 60
_MAX_DURATION = 315_360_000  # 10 years — API hard cap (= "no practical timer")

_LAST: dict[str, Any] = {
    "action": None,
    "ok": None,
    "detail": None,
    "at": None,
    "chaster_type": None,
    "chaster_remaining": None,
    "chaster_frozen": None,
    "chaster_time_hidden": None,
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
    chaster_frozen: bool | None = None,
    chaster_time_hidden: bool | None = None,
) -> dict[str, Any]:
    _LAST.update(
        {
            "action": action,
            "ok": ok,
            "detail": detail,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "chaster_type": chaster_type,
            "chaster_remaining": chaster_remaining,
            "chaster_frozen": chaster_frozen,
            "chaster_time_hidden": chaster_time_hidden,
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


# When Chaster hides the timer, R+D API cannot set isTimeDisplayed — approximate
# by parking the box on a long dummy duration until time is revealed again.
_HIDDEN_DURATION = 86400 * 365 * 5  # 5 years (looks indefinite on the box)

# Last observed Chaster freeze/hide — used to catch unfreeze/reveal without history events
_LAST_CHASTER_FLAGS: dict[str, bool | None] = {
    "frozen": None,
    "time_hidden": None,
}


async def chaster_lock_snapshot(
    chaster: ChasterClient | None,
) -> dict[str, Any] | None:
    """Read Chaster remaining / frozen / timer-hidden for R+D mirroring."""
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
                    lock = await chaster.get_lock(
                        str(raw.get("_id") or raw.get("id"))
                    ) or raw
        if not isinstance(lock, dict):
            return None
        status = str(lock.get("status") or "").lower()
        if status in ("unlocked", "archived", "deserted", "ended"):
            return {
                "status": status,
                "remaining": None,
                "frozen": False,
                "time_hidden": False,
                "end_date": None,
            }
        frozen = bool(lock.get("isFrozen"))
        # Chaster: displayRemainingTime True = shown; False = hidden
        display = lock.get("displayRemainingTime")
        time_hidden = display is False
        rem: int | None = None
        end = lock.get("endDate")
        if end:
            end_dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
            rem = int((end_dt - datetime.now(timezone.utc)).total_seconds())
            if rem <= 0:
                rem = None
        elif frozen:
            rem = _MAX_DURATION
        return {
            "status": status or "locked",
            "remaining": rem,
            "frozen": frozen,
            "time_hidden": time_hidden,
            "end_date": end,
        }
    except Exception:  # noqa: BLE001
        log.exception("Failed to read Chaster lock snapshot")
        return None


async def chaster_remaining_seconds(chaster: ChasterClient | None) -> int | None:
    snap = await chaster_lock_snapshot(chaster)
    if not snap:
        return None
    return snap.get("remaining")


def _target_duration_from_chaster(snap: dict[str, Any]) -> tuple[int | None, str]:
    """
    Map Chaster state → R+D duration.

    R+D public API only supports duration (no freeze / hide flags), so:
    - frozen: park at API max (10y) so the box doesn't keep counting down
    - time hidden: park on a long dummy duration until revealed
    - normal: real remaining
    """
    rem = snap.get("remaining")
    frozen = bool(snap.get("frozen"))
    hidden = bool(snap.get("time_hidden"))
    if hidden:
        # Don't leak the real countdown on the box display
        return _HIDDEN_DURATION, "hidden-timer placeholder"
    if frozen:
        # Freeze has no R+D flag — park far out; unfreeze restores Chaster remaining.
        return _MAX_DURATION, "frozen placeholder"
    if rem is None:
        return None, "no remaining"
    return _clamp_duration(int(rem)), "chaster remaining"


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


def _manual_only(rad: RadLockboxClient) -> bool:
    return bool(getattr(rad.settings, "rad_manual_only", False))


async def maybe_resync_after_chaster_flags(
    rad: RadLockboxClient,
    chaster: ChasterClient | None,
) -> dict[str, Any] | None:
    """If Chaster just unfroze or unhid the timer, force a duration resync.

    Works in manual-only mode too — those transitions are the exceptions where
    we pull real Chaster remaining onto the box.
    """
    if not rad.configured:
        return _stamp(
            action="set_duration",
            ok=False,
            detail="RAD_API_TOKEN not set on server — add Render env vars",
            chaster_type="config",
        )
    if not _sync_on(rad):
        return _stamp(
            action="set_duration",
            ok=False,
            detail="RAD_LOCKBOX_SYNC_ENABLED is false",
            chaster_type="config",
        )
    snap = await chaster_lock_snapshot(chaster)
    if not snap:
        return None
    frozen = bool(snap.get("frozen"))
    hidden = bool(snap.get("time_hidden"))
    prev_f = _LAST_CHASTER_FLAGS.get("frozen")
    prev_h = _LAST_CHASTER_FLAGS.get("time_hidden")
    _LAST_CHASTER_FLAGS["frozen"] = frozen
    _LAST_CHASTER_FLAGS["time_hidden"] = hidden

    # First observation: seed flags + apply current freeze/hide/remaining once
    # (covers events missed while the server had no RAD token / was asleep).
    if prev_f is None and prev_h is None:
        if frozen or hidden or snap.get("remaining"):
            reason = "boot_catchup"
            if frozen:
                reason += "+lock_frozen"
            if hidden:
                reason += "+timer_hidden"
            return await sync_duration_from_chaster(
                rad, chaster, reason=reason, force=True
            )
        return None

    reasons: list[str] = []
    if prev_f is True and frozen is False:
        reasons.append("lock_unfrozen")
    if prev_h is True and hidden is False:
        reasons.append("timer_revealed")
    if prev_f is False and frozen is True:
        reasons.append("lock_frozen")
    if prev_h is False and hidden is True:
        reasons.append("timer_hidden")
    if not reasons:
        # While frozen/hidden, keep rewinding the placeholder so the box
        # can't bleed down (even in manual-only).
        if frozen or hidden:
            return await sync_duration_from_chaster(
                rad,
                chaster,
                reason="frozen_hold" if frozen else "hidden_hold",
                force=True,
            )
        return None
    return await sync_duration_from_chaster(
        rad, chaster, reason="+".join(reasons), force=True
    )


async def sync_duration_from_chaster(
    rad: RadLockboxClient,
    chaster: ChasterClient | None,
    *,
    reason: str = "time_sync",
    force: bool = False,
) -> dict[str, Any]:
    """PATCH active R+D session duration from Chaster (handles freeze + hidden timer)."""
    if _manual_only(rad) and not force:
        return _stamp(
            action="set_duration",
            ok=True,
            detail="Manual-only mode — Chaster timer sync skipped",
            chaster_type=reason,
        )
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
    snap = await chaster_lock_snapshot(chaster)
    if not snap:
        return _stamp(
            action="set_duration",
            ok=False,
            detail="Could not read Chaster lock",
            chaster_type=reason,
        )
    rem = snap.get("remaining")
    frozen = bool(snap.get("frozen"))
    hidden = bool(snap.get("time_hidden"))
    duration, mode = _target_duration_from_chaster(snap)
    if duration is None:
        return _stamp(
            action="set_duration",
            ok=False,
            detail="No Chaster remaining time available",
            chaster_type=reason,
            chaster_remaining=rem,
            chaster_frozen=frozen,
            chaster_time_hidden=hidden,
        )
    try:
        session = await rad.get_active_session()
        if not session or not session.get("isActive"):
            return _stamp(
                action="set_duration",
                ok=False,
                detail="No active R+D session to update",
                chaster_type=reason,
                chaster_remaining=rem,
                chaster_frozen=frozen,
                chaster_time_hidden=hidden,
            )
        state = str(session.get("lockState") or "").lower()
        if state != "locked":
            return _stamp(
                action="set_duration",
                ok=False,
                detail=f"R+D session state is {state or '?'}, not locked",
                chaster_type=reason,
                chaster_remaining=rem,
                chaster_frozen=frozen,
                chaster_time_hidden=hidden,
            )
        current = session.get("duration")
        # Soft-freeze: always rewrite while frozen so the box timer can't run down.
        # Hidden: keep parked on the placeholder.
        skip_tol = 5 if (frozen or hidden) else 30
        try:
            if current is not None and abs(int(current) - duration) < skip_tol:
                return _stamp(
                    action="set_duration",
                    ok=True,
                    detail=f"Already synced ({mode}, {duration}s)",
                    chaster_type=reason,
                    chaster_remaining=rem,
                    chaster_frozen=frozen,
                    chaster_time_hidden=hidden,
                )
        except (TypeError, ValueError):
            pass
        await rad.set_duration(duration)
        bits = [mode, f"{duration}s"]
        if frozen:
            bits.append("Chaster FROZEN")
        if hidden:
            bits.append("Chaster timer HIDDEN")
        detail = "Set R+D duration — " + ", ".join(bits)
        log.info("R+D duration sync (%s): %s", reason, detail)
        return _stamp(
            action="set_duration",
            ok=True,
            detail=detail,
            chaster_type=reason,
            chaster_remaining=rem,
            chaster_frozen=frozen,
            chaster_time_hidden=hidden,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("R+D duration sync failed")
        return _stamp(
            action="set_duration",
            ok=False,
            detail=str(exc),
            chaster_type=reason,
            chaster_remaining=rem,
            chaster_frozen=frozen,
            chaster_time_hidden=hidden,
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

    snap = await chaster_lock_snapshot(chaster) if not _manual_only(rad) else None
    rem = snap.get("remaining") if snap else None
    frozen = bool(snap.get("frozen")) if snap else False
    hidden = bool(snap.get("time_hidden")) if snap else False
    if _manual_only(rad):
        duration = _MAX_DURATION
        mode = "manual (no timer — 10y park)"
    elif snap:
        duration, mode = _target_duration_from_chaster(snap)
    else:
        duration, mode = None, "chaster remaining"

    template_id = await ensure_template_id(rad)
    if template_id is None:
        return _stamp(
            action="lock",
            ok=False,
            detail="No R+D lock template available (API still needs one to start a session)",
            chaster_type=reason,
            chaster_remaining=rem,
            chaster_frozen=frozen,
            chaster_time_hidden=hidden,
        )

    try:
        session = await rad.get_active_session()
        if session and session.get("isActive"):
            state = str(session.get("lockState") or "").lower()
            if state == "locked":
                # Already locked — just push Chaster time / freeze / hide mapping
                if duration is not None:
                    await rad.set_duration(duration)
                    return _stamp(
                        action="lock",
                        ok=True,
                        detail=f"Already locked — synced ({mode}, {duration}s)",
                        chaster_type=reason,
                        chaster_remaining=rem,
                        chaster_frozen=frozen,
                        chaster_time_hidden=hidden,
                    )
                return _stamp(
                    action="lock",
                    ok=True,
                    detail="R+D already locked (no Chaster time to sync)",
                    chaster_type=reason,
                    chaster_remaining=rem,
                    chaster_frozen=frozen,
                    chaster_time_hidden=hidden,
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
                    chaster_frozen=frozen,
                    chaster_time_hidden=hidden,
                )
            detail = f"Re-locked; {mode} → {duration}s"
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
            chaster_frozen=frozen,
            chaster_time_hidden=hidden,
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
                        f"Session active after lock quirk; synced "
                        f"({mode}, {duration}s)"
                    ),
                    chaster_type=reason,
                    chaster_remaining=rem,
                    chaster_frozen=frozen,
                    chaster_time_hidden=hidden,
                )
            except Exception as exc2:  # noqa: BLE001
                msg = f"{msg} | duration sync: {exc2}"
        if "already have an active lock" in msg.lower() and duration is not None:
            try:
                await rad.set_duration(duration)
                return _stamp(
                    action="lock",
                    ok=True,
                    detail=f"Active session kept; synced ({mode}, {duration}s)",
                    chaster_type=reason,
                    chaster_remaining=rem,
                    chaster_frozen=frozen,
                    chaster_time_hidden=hidden,
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
                    chaster_frozen=frozen,
                    chaster_time_hidden=hidden,
                )
        log.exception("R+D re-lock after %s failed", reason)
        return _stamp(
            action="lock",
            ok=False,
            detail=msg,
            chaster_type=reason,
            chaster_remaining=rem,
            chaster_frozen=frozen,
            chaster_time_hidden=hidden,
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

# Even in manual-only mode, apply freeze/hide placeholders and restore on release.
_FORCE_RESYNC_TYPES = frozenset(
    {
        "lock_frozen",
        "lock_unfrozen",
        "timer_hidden",
        "timer_revealed",
    }
)


async def handle_chaster_events(
    rad: RadLockboxClient,
    events: list[dict[str, Any]],
    *,
    chaster: ChasterClient | None = None,
) -> list[dict[str, Any]]:
    """Mirror relevant Chaster history events onto the R+D lockbox."""
    if not events:
        return []
    if not rad.configured:
        log.warning(
            "Chaster lock events ignored — RAD_API_TOKEN not set (%s)",
            [str(e.get("type") or "") for e in events[:5]],
        )
        _stamp(
            action="skip",
            ok=False,
            detail="RAD_API_TOKEN not set — events not synced",
            chaster_type=",".join(str(e.get("type") or "") for e in events[:3]),
        )
        return []
    if not _sync_on(rad):
        log.warning("Chaster lock events ignored — RAD_LOCKBOX_SYNC_ENABLED=false")
        return []

    hygiene = bool(getattr(rad.settings, "rad_sync_hygiene", True))
    session_sync = bool(getattr(rad.settings, "rad_sync_session_lock", False))
    manual = _manual_only(rad)
    results: list[dict[str, Any]] = []
    synced_time = False

    for ev in events:
        etype = str(ev.get("type") or "")
        log.info("Lockbox sync handling Chaster event type=%s", etype)
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
        elif etype in _FORCE_RESYNC_TYPES:
            # Unfreeze / unhide → always apply real Chaster remaining (even manual-only)
            results.append(
                await sync_duration_from_chaster(
                    rad, chaster, reason=etype, force=True
                )
            )
            synced_time = True
        elif (
            not manual
            and etype in _TIME_SYNC_TYPES
            and not synced_time
        ):
            results.append(
                await sync_duration_from_chaster(rad, chaster, reason=etype)
            )
            synced_time = True

    return results
