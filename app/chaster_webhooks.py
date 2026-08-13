"""Chaster partner-extension webhooks (push) → lockbox sync + lock-watch.

Docs: https://docs.chaster.app/api/extensions-api/create-your-extension/webhooks/
Configure in Developer → Extension URLs:
  POST https://<host>/api/chaster/webhook
  Basic auth: CHASTER_WEBHOOK_USER / CHASTER_WEBHOOK_PASSWORD
  Event: action_log.created (also accepts extension_session.*)
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any

from fastapi import HTTPException, Request
from fastapi.security import HTTPBasicCredentials

log = logging.getLogger(__name__)


def webhook_auth_configured(settings: Any) -> bool:
    user = (getattr(settings, "chaster_webhook_user", None) or "").strip()
    password = (getattr(settings, "chaster_webhook_password", None) or "").strip()
    return bool(user and password)


def verify_webhook_basic(
    settings: Any, credentials: HTTPBasicCredentials | None
) -> None:
    """Require HTTP Basic when credentials are configured; else 503."""
    if not webhook_auth_configured(settings):
        raise HTTPException(
            status_code=503,
            detail="Webhook auth not configured (CHASTER_WEBHOOK_USER/PASSWORD)",
        )
    expected_user = (settings.chaster_webhook_user or "").strip()
    expected_pass = (settings.chaster_webhook_password or "").strip()
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    user_ok = secrets.compare_digest(credentials.username or "", expected_user)
    pass_ok = secrets.compare_digest(credentials.password or "", expected_pass)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )


def _unwrap_event(body: dict[str, Any]) -> dict[str, Any]:
    """Accept {payload: Event} or the Event object itself."""
    if not isinstance(body, dict):
        return {}
    inner = body.get("payload")
    if isinstance(inner, dict) and (
        "event" in inner or "data" in inner or "actionLog" in inner
    ):
        return inner
    return body


def parse_webhook_body(body: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a Chaster webhook into:
      {event, request_id, session_id, action_log|None, raw}
    """
    ev = _unwrap_event(body)
    event_name = str(ev.get("event") or "").strip()
    data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
    action_log = data.get("actionLog") if isinstance(data, dict) else None
    if action_log is None and isinstance(ev.get("actionLog"), dict):
        action_log = ev.get("actionLog")
    if not event_name and isinstance(action_log, dict):
        event_name = "action_log.created"
    return {
        "event": event_name,
        "request_id": str(ev.get("requestId") or body.get("requestId") or ""),
        "session_id": str(
            (data or {}).get("sessionId")
            or ev.get("sessionId")
            or ""
        ),
        "action_log": action_log if isinstance(action_log, dict) else None,
        "raw": ev,
    }


def action_log_matches_lock(
    action_log: dict[str, Any], *, lock_id: str
) -> bool:
    """If CHASTER_LOCK_ID is set, ignore logs for other locks."""
    want = (lock_id or "").strip()
    if not want:
        return True
    got = str(action_log.get("lock") or "").strip()
    return not got or got == want


def history_event_from_action_log(action_log: dict[str, Any]) -> dict[str, Any]:
    """Shape webhook action logs like GET /locks/:id/history rows."""
    return {
        "_id": action_log.get("_id"),
        "type": action_log.get("type"),
        "payload": action_log.get("payload") or {},
        "lock": action_log.get("lock"),
        "role": action_log.get("role"),
        "extension": action_log.get("extension"),
        "title": action_log.get("title"),
        "description": action_log.get("description"),
        "createdAt": action_log.get("createdAt"),
        "prefix": action_log.get("prefix"),
        "user": action_log.get("user"),
    }


async def handle_chaster_webhook(
    *,
    settings: Any,
    body: dict[str, Any],
    chaster: Any,
    rad: Any | None,
    agent: Any | None = None,
    store: Any | None = None,
    scene: Any | None = None,
    memory: Any | None = None,
) -> dict[str, Any]:
    """Process one webhook. Lockbox sync is awaited; AI react is best-effort."""
    parsed = parse_webhook_body(body)
    event_name = parsed["event"]
    out: dict[str, Any] = {
        "ok": True,
        "event": event_name,
        "request_id": parsed["request_id"],
        "handled": [],
    }

    if event_name == "action_log.created" and parsed["action_log"]:
        alog = parsed["action_log"]
        if not action_log_matches_lock(
            alog, lock_id=getattr(settings, "chaster_lock_id", "") or ""
        ):
            out["handled"].append("ignored_other_lock")
            return out
        history_ev = history_event_from_action_log(alog)
        etype = str(history_ev.get("type") or "")
        log.info(
            "Chaster webhook action_log type=%s id=%s",
            etype,
            history_ev.get("_id"),
        )

        from app.lock_watch import mark_history_events_seen

        mark_history_events_seen([history_ev])

        if rad is not None:
            from app.lockbox_sync import handle_chaster_events

            try:
                results = await handle_chaster_events(
                    rad, [history_ev], chaster=chaster
                )
                out["lockbox"] = results
                out["handled"].append("lockbox_sync")
            except Exception:  # noqa: BLE001
                log.exception("Webhook lockbox sync failed")
                out["ok"] = False
                out["handled"].append("lockbox_sync_error")

        # Flag hold / freeze placeholders even if history type was unexpected
        if rad is not None:
            try:
                from app.lockbox_sync import maybe_resync_after_chaster_flags

                flag_r = await maybe_resync_after_chaster_flags(rad, chaster)
                if flag_r:
                    out["flag_sync"] = flag_r
                    out["handled"].append("flag_sync")
            except Exception:  # noqa: BLE001
                log.debug("Webhook flag sync skipped", exc_info=True)

        if agent is not None and store is not None and scene is not None and memory:
            # LLM can exceed Chaster's 10s webhook timeout — run in background
            async def _react() -> None:
                try:
                    from app.lock_watch import react_to_lock_events

                    await react_to_lock_events(
                        agent=agent,
                        store=store,
                        scene=scene,
                        memory=memory,
                        chaster=chaster,
                        events=[history_ev],
                        rad=None,
                    )
                except Exception:  # noqa: BLE001
                    log.exception("Webhook AI react failed")

            asyncio.create_task(_react())
            out["handled"].append("ai_react_queued")
        return out

    if event_name.startswith("extension_session."):
        out["handled"].append("session_event")
        if rad is not None:
            try:
                from app.lockbox_sync import (
                    maybe_resync_after_chaster_flags,
                    sync_duration_from_chaster,
                )

                flag_r = await maybe_resync_after_chaster_flags(rad, chaster)
                if flag_r:
                    out["flag_sync"] = flag_r
                elif not getattr(settings, "rad_manual_only", False):
                    out["duration_sync"] = await sync_duration_from_chaster(
                        rad, chaster, reason=event_name, force=True
                    )
                out["handled"].append("session_resync")
            except Exception:  # noqa: BLE001
                log.exception("Webhook session resync failed")
                out["ok"] = False
        return out

    out["handled"].append("ignored")
    return out


async def read_json_body(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    return data
