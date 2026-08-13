"""Chaster → Research & Desire Lockbox sync (no AI).

Temporary bridge:
- Chaster hygiene open  → unlock R+D lockbox
- Chaster hygiene close → re-lock R+D with configured template
Optional:
- Chaster unlocked / locked → unlock / lock R+D
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.rad_lockbox import RadLockboxClient

log = logging.getLogger(__name__)

_LAST: dict[str, Any] = {
    "action": None,
    "ok": None,
    "detail": None,
    "at": None,
    "chaster_type": None,
}


def last_sync_status() -> dict[str, Any]:
    return dict(_LAST)


def _stamp(
    *,
    action: str,
    ok: bool,
    detail: str,
    chaster_type: str | None = None,
) -> dict[str, Any]:
    _LAST.update(
        {
            "action": action,
            "ok": ok,
            "detail": detail,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "chaster_type": chaster_type,
        }
    )
    return dict(_LAST)


def _sync_on(rad: RadLockboxClient) -> bool:
    return bool(
        rad.configured
        and getattr(rad.settings, "rad_lockbox_sync_enabled", False)
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


async def relock_after_hygiene(
    rad: RadLockboxClient,
    *,
    reason: str = "hygiene_closed",
    force: bool = False,
) -> dict[str, Any]:
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
    if rad.lock_settings_id is None:
        return _stamp(
            action="lock",
            ok=False,
            detail="RAD_LOCK_SETTINGS_ID missing — cannot re-lock",
            chaster_type=reason,
        )
    try:
        session = await rad.get_active_session()
        if session and session.get("isActive"):
            state = str(session.get("lockState") or "").lower()
            if state == "locked":
                return _stamp(
                    action="lock",
                    ok=True,
                    detail="R+D already locked",
                    chaster_type=reason,
                )
            # Active but not locked (e.g. pending) — try unlock first then lock
            try:
                await rad.unlock()
            except Exception:  # noqa: BLE001
                pass
        await rad.lock()
        log.info("R+D lockbox re-locked after %s", reason)
        return _stamp(
            action="lock",
            ok=True,
            detail="Re-locked R+D lockbox",
            chaster_type=reason,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("R+D re-lock after %s failed", reason)
        return _stamp(
            action="lock",
            ok=False,
            detail=str(exc),
            chaster_type=reason,
        )


async def handle_chaster_events(
    rad: RadLockboxClient, events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Mirror relevant Chaster history events onto the R+D lockbox."""
    if not events or not _sync_on(rad):
        return []

    hygiene = bool(getattr(rad.settings, "rad_sync_hygiene", True))
    session_sync = bool(getattr(rad.settings, "rad_sync_session_lock", False))
    results: list[dict[str, Any]] = []

    for ev in events:
        etype = str(ev.get("type") or "")
        if hygiene and etype == "temporary_opening_opened":
            results.append(await unlock_for_hygiene(rad, reason=etype))
        elif hygiene and etype == "temporary_opening_locked":
            results.append(await relock_after_hygiene(rad, reason=etype))
        elif session_sync and etype == "unlocked":
            results.append(await unlock_for_hygiene(rad, reason=etype))
        elif session_sync and etype == "locked":
            results.append(await relock_after_hygiene(rad, reason=etype))

    return results
