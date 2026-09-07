"""Chaster Duo Domme webhooks (push) → lockbox sync + lock-watch.

Docs: https://docs.chaster.app/api/extensions-api/create-your-extension/webhooks/
Configure on the Duo Domme developer app → Extension URLs:
  POST https://<host>/api/chaster/webhook
  Event: action_log.created (also accepts extension_session.*)
  Basic auth optional unless CHASTER_WEBHOOK_REQUIRE_AUTH=true
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
    """Optional HTTP Basic (Duo Domme often sends URL-only unless auth is set)."""
    require = bool(getattr(settings, "chaster_webhook_require_auth", False))
    if not require:
        # If Chaster does send Basic auth and we have a password, still verify it.
        if credentials is None or not webhook_auth_configured(settings):
            return
    elif not webhook_auth_configured(settings):
        raise HTTPException(
            status_code=503,
            detail="Webhook auth required but CHASTER_WEBHOOK_PASSWORD is empty",
        )

    if not webhook_auth_configured(settings):
        return
    expected_user = (settings.chaster_webhook_user or "").strip()
    expected_pass = (settings.chaster_webhook_password or "").strip()
    if credentials is None:
        if require:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized",
                headers={"WWW-Authenticate": "Basic"},
            )
        return
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


def extract_lock_id(raw: Any) -> str:
    """Lock id from a string or a lock object ``{_id,id}``. Do not pass a full action log."""
    if raw is None:
        return ""
    if isinstance(raw, dict):
        nested = raw.get("lock")
        if nested is not None and nested is not raw:
            got = extract_lock_id(nested)
            if got:
                return got
        for key in ("_id", "id", "lockId"):
            val = raw.get(key)
            if val is not None and not isinstance(val, (dict, list)):
                text = str(val).strip()
                if text:
                    return text
        return ""
    return str(raw).strip()


def lock_id_from_session_payload(data: dict[str, Any], raw: dict[str, Any]) -> str:
    session = data.get("session") if isinstance(data.get("session"), dict) else {}
    for candidate in (
        data.get("lock"),
        session.get("lock") if isinstance(session, dict) else None,
        data.get("lockId"),
        raw.get("lock"),
        session.get("lockId") if isinstance(session, dict) else None,
    ):
        lid = extract_lock_id(candidate)
        if lid:
            return lid
    return ""


def _normalize_event_name(name: str) -> str:
    aliases = {
        "actionLog.created": "action_log.created",
        "extensionSession.created": "extension_session.created",
        "extensionSession.updated": "extension_session.updated",
        "extensionSession.deleted": "extension_session.deleted",
    }
    return aliases.get(name, name)


def parse_webhook_body(body: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a Chaster webhook into:
      {event, request_id, session_id, lock_id, action_log|None, raw}
    """
    ev = _unwrap_event(body)
    event_name = _normalize_event_name(str(ev.get("event") or "").strip())
    data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
    action_log = data.get("actionLog") if isinstance(data, dict) else None
    if action_log is None and isinstance(ev.get("actionLog"), dict):
        action_log = ev.get("actionLog")
    if not event_name and isinstance(action_log, dict):
        event_name = "action_log.created"
    lock_id = ""
    if isinstance(action_log, dict):
        lock_id = extract_lock_id(action_log.get("lock"))
    if not lock_id and isinstance(data, dict):
        lock_id = lock_id_from_session_payload(data, ev)
    return {
        "event": event_name,
        "request_id": str(ev.get("requestId") or body.get("requestId") or ""),
        "session_id": str(
            (data or {}).get("sessionId")
            or ev.get("sessionId")
            or ""
        ),
        "lock_id": lock_id,
        "action_log": action_log if isinstance(action_log, dict) else None,
        "raw": ev,
    }


def action_log_matches_lock(
    action_log: dict[str, Any], *, lock_id: str
) -> bool:
    """Always process every lock — chat/history are already scoped per lock.

    ``lock_id`` is unused; kept so callers that still pass CHASTER_LOCK_ID
    do not drop a new session's events.
    """
    del action_log, lock_id
    return True


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


async def _lock_id_for_extension_session(chaster: Any, session_id: str) -> str:
    sid = (session_id or "").strip()
    if not sid or chaster is None:
        return ""
    search = getattr(chaster, "search_extension_sessions", None)
    if search is None:
        return ""
    sessions = await search()
    for session in sessions or []:
        if not isinstance(session, dict):
            continue
        if str(session.get("sessionId") or "").strip() != sid:
            continue
        return extract_lock_id(session.get("lock"))
    return ""


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
        lock_id = parsed.get("lock_id") or extract_lock_id(alog.get("lock"))
        history_ev = history_event_from_action_log(alog)
        from app.lockbox_sync import normalize_history_type

        etype = normalize_history_type(history_ev)
        log.info(
            "Chaster webhook action_log type=%s id=%s lock=%s",
            etype,
            history_ev.get("_id"),
            lock_id,
        )
        out["action_type"] = etype
        out["lock_id"] = lock_id

        from app.lock_watch import mark_history_events_seen

        mark_history_events_seen([history_ev], lock_id=lock_id)

        # Primary path: freeze / time / hygiene via lockbox sync (force)
        if rad is not None:
            from app.lockbox_sync import (
                handle_chaster_events,
                is_lockbox_priority_event,
                maybe_resync_after_chaster_flags,
            )

            priority = is_lockbox_priority_event(etype)
            try:
                results = await handle_chaster_events(
                    rad,
                    [history_ev],
                    chaster=chaster,
                    source="webhook",
                )
                out["lockbox"] = results
                out["handled"].append(
                    "lockbox_priority" if priority else "lockbox_sync"
                )
            except Exception:  # noqa: BLE001
                log.exception("Webhook lockbox sync failed")
                out["ok"] = False
                out["handled"].append("lockbox_sync_error")

            # Freeze/hide flag edges (covers missed action-log type variants)
            try:
                flag_r = await maybe_resync_after_chaster_flags(rad, chaster)
                if flag_r:
                    out["flag_sync"] = flag_r
                    out["handled"].append("flag_sync")
            except Exception:  # noqa: BLE001
                log.debug("Webhook flag sync skipped", exc_info=True)

        if agent is not None and store is not None and scene is not None and memory:
            from app.lock_scope import bind_lock_scope

            bind_lock_scope(
                lock_id=lock_id,
                session_id=parsed["session_id"],
            )
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
        data = parsed["raw"].get("data") if isinstance(parsed["raw"].get("data"), dict) else {}
        lock_id = parsed.get("lock_id") or lock_id_from_session_payload(
            data if isinstance(data, dict) else {},
            parsed["raw"],
        )
        if (not lock_id) and parsed["session_id"] and chaster is not None:
            try:
                lock_id = await _lock_id_for_extension_session(
                    chaster, parsed["session_id"]
                )
            except Exception:  # noqa: BLE001
                log.debug("Session webhook lock lookup failed", exc_info=True)
        out["lock_id"] = lock_id
        if lock_id or parsed["session_id"]:
            from app.lock_scope import bind_lock_scope

            bind_lock_scope(lock_id=lock_id, session_id=parsed["session_id"])
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
        if (
            agent is not None
            and store is not None
            and scene is not None
            and memory
            and chaster is not None
        ):
            async def _react_session() -> None:
                try:
                    from app.lock_watch import fetch_new_events, react_to_lock_events

                    events = await fetch_new_events(chaster, lock_id=lock_id)
                    if not events:
                        return
                    await react_to_lock_events(
                        agent=agent,
                        store=store,
                        scene=scene,
                        memory=memory,
                        chaster=chaster,
                        events=events,
                        rad=None,
                    )
                except Exception:  # noqa: BLE001
                    log.exception("Webhook session AI react failed")

            asyncio.create_task(_react_session())
            out["handled"].append("ai_react_queued")
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
