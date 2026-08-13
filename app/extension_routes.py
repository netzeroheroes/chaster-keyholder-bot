"""Partner-extension HTTP routes: /ext chat + /ext/config settings."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.agent import ChatAgent
from app.autopilot import autopilot_status, run_unprompted_tick
from app.bridge import GroupBridge
from app.chaster import ChasterClient
from app.chat_service import handle_chat_turn
from app.config import Settings
from app.extension_auth import (
    ExtensionAuthCache,
    ExtSession,
    public_session_view,
    resolve_main_token,
)
from app.images import ImageService
from app.lockbox_sync import (
    last_sync_status,
    relock_after_hygiene,
    sync_duration_from_chaster,
    unlock_for_hygiene,
)
from app.memory import LongTermMemory
from app.rad_lockbox import RadLockboxClient
from app.roles import Room, can_access
from app.runtime_controls import RuntimeControls
from app.scene import SceneState
from app.sessions import SessionStore
from app.typing_presence import clear_typing, list_typing, set_typing

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
EXT_DIR = STATIC_DIR / "ext"

# Keys we accept into Chaster extension config + runtime_controls
_CONFIG_KEYS = (
    "auto_punish_enabled",
    "auto_punish_seconds",
    "autopilot_enabled",
    "autopilot_timezone",
    "autopilot_window_start",
    "autopilot_window_end",
    "autopilot_min_minutes",
    "autopilot_max_minutes",
    "autopilot_allow_chaster",
    "autopilot_chaster_chance",
    "autopilot_punish_seconds",
    "min_add_time_seconds",
    "max_add_time_seconds",
    "default_add_time_seconds",
    "default_remove_time_seconds",
    "soft_add_time_seconds",
    "hard_add_time_seconds",
    "bot_name",
    "domme_title",
)


class ExtChatBody(BaseModel):
    main_token: str = Field(min_length=8)
    message: str = Field(min_length=1)
    room: Room = "group"


class ExtSessionBody(BaseModel):
    main_token: str = Field(min_length=8)
    room: Room = "group"


class ExtTypingBody(BaseModel):
    main_token: str = Field(min_length=8)
    room: Room = "group"
    active: bool = True
    label: str = ""


class ExtLockboxBody(BaseModel):
    main_token: str = Field(min_length=8)
    action: str = ""  # lock | unlock | status


class ExtConfigGetBody(BaseModel):
    partner_configuration_token: str = Field(min_length=8)


class ExtConfigSaveBody(BaseModel):
    partner_configuration_token: str = Field(min_length=8)
    config: dict[str, Any]


def _api_detail(exc: BaseException) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if "not linked" in text.lower() or "CHASTER_ACCESS_TOKEN" in text:
        return (
            "Chaster developer token missing on the server. "
            "In Render, set CHASTER_ACCESS_TOKEN to Developer → your app → Tokens "
            "(same application as this extension — not a random user OAuth token)."
        )
    if "401" in text or "403" in text:
        return (
            f"{text} — Use Configure on YOUR partner extension (the one whose "
            "Main/Config URLs point here). Duo Domme lock actions are separate."
        )
    return text[:500]


def _ext_csp(settings: Settings) -> str:
    ancestors = (settings.extension_frame_ancestors or "").strip()
    if not ancestors:
        ancestors = "'none'"
    return f"frame-ancestors {ancestors};"


async def _require_session(
    chaster: ChasterClient,
    cache: ExtensionAuthCache,
    settings: Settings,
    main_token: str,
) -> ExtSession:
    if settings.extension_dev_bypass and main_token.startswith("dev:"):
        # Local testing: main_token = "dev:keyholder" or "dev:wearer"
        role = "keyholder" if "keyholder" in main_token else "wearer"
        from app.extension_auth import ExtSession
        import time

        return ExtSession(
            main_token=main_token,
            role=role,  # type: ignore[arg-type]
            user_id="dev",
            session_id="dev",
            lock_id="",
            wearer_username="lockee",
            keyholder_username="keyholder",
            config={},
            fetched_at=time.time(),
        )
    try:
        return await resolve_main_token(chaster, main_token, cache=cache)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=401,
            detail="Open this page from Chaster (invalid or expired mainToken).",
        ) from exc


def register_extension_routes(
    api: FastAPI,
    *,
    settings: Settings,
    agent: ChatAgent,
    store: SessionStore,
    scene: SceneState,
    memory: LongTermMemory,
    bridge: GroupBridge,
    images: ImageService,
    chaster: ChasterClient,
    controls: RuntimeControls,
    rad: RadLockboxClient | None = None,
) -> None:
    cache = ExtensionAuthCache(ttl_seconds=120)

    @api.middleware("http")
    async def extension_security_headers(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path or ""
        if path.startswith("/ext") or path.startswith("/api/ext"):
            response.headers["Content-Security-Policy"] = _ext_csp(settings)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            # Discourage indexing of extension surfaces
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        # Keep extension UI assets from sticking on old ?v= bundles inside Chaster.
        if path.startswith("/static/ext/"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"
        return response

    def _no_store_html(path: Path) -> FileResponse:
        resp = FileResponse(path)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp

    @api.get("/ext")
    @api.get("/ext/")
    async def ext_main() -> FileResponse:
        path = EXT_DIR / "index.html"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Extension UI missing")
        return _no_store_html(path)

    @api.get("/ext/config")
    @api.get("/ext/config/")
    async def ext_config_page() -> FileResponse:
        path = EXT_DIR / "config.html"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Config UI missing")
        return _no_store_html(path)

    @api.post("/api/ext/session")
    async def ext_session(body: ExtSessionBody) -> dict:
        sess = await _require_session(chaster, cache, settings, body.main_token)
        # Keyholder session config on Chaster → live autopilot/auto-punish controls
        if sess.app_role == "domme" and sess.config:
            try:
                _sync_controls_from_config(_merged_settings(sess.config))
            except Exception:  # noqa: BLE001
                logging.getLogger(__name__).debug(
                    "Could not sync controls from session", exc_info=True
                )
        return {
            "ok": True,
            "session": public_session_view(sess),
            "bot_name": memory.bot_name or "Keyholder",
            "domme_title": memory.domme_title or "",
            "autopilot": autopilot_status(settings),
        }

    @api.post("/api/ext/history")
    async def ext_history_post(body: ExtSessionBody) -> dict:
        sess = await _require_session(chaster, cache, settings, body.main_token)
        room: Room = body.room
        if not can_access(sess.app_role, room):
            raise HTTPException(
                status_code=403,
                detail="Only the Chaster keyholder can open private chat.",
            )
        speaker = "Domme" if sess.app_role == "domme" else "Sub"
        return {
            "room": room,
            "role": sess.app_role,
            "chaster_role": sess.role,
            "messages": store.get_display(room),
            "typing": list_typing(room, exclude=speaker),
        }

    @api.post("/api/ext/typing")
    async def ext_typing(body: ExtTypingBody) -> dict:
        sess = await _require_session(chaster, cache, settings, body.main_token)
        room: Room = body.room
        if not can_access(sess.app_role, room):
            raise HTTPException(
                status_code=403,
                detail="Only the Chaster keyholder can use private chat.",
            )
        speaker = "Domme" if sess.app_role == "domme" else "Sub"
        label = (
            (body.label or sess.speaker_username or speaker).strip()[:40]
        )
        if body.active:
            set_typing(room, speaker, label)
        else:
            clear_typing(room, speaker)
        return {
            "ok": True,
            "typing": list_typing(room, exclude=speaker),
        }

    @api.post("/api/ext/chat")
    async def ext_chat(body: ExtChatBody) -> dict:
        sess = await _require_session(chaster, cache, settings, body.main_token)
        room: Room = body.room
        if not can_access(sess.app_role, room):
            raise HTTPException(
                status_code=403,
                detail="Only the Chaster keyholder can use private chat.",
            )
        clear_typing(room, "Domme" if sess.app_role == "domme" else "Sub")
        try:
            result = await handle_chat_turn(
                agent=agent,
                store=store,
                scene=scene,
                memory=memory,
                bridge=bridge,
                images=images,
                chaster=chaster,
                role=sess.app_role,
                room=room,
                message=body.message,
                chaster_role=sess.role,
                chaster_username=sess.speaker_username,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return result

    @api.post("/api/ext/config/get")
    async def ext_config_get(body: ExtConfigGetBody) -> dict:
        try:
            raw = await chaster.get_partner_configuration(
                body.partner_configuration_token
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=401, detail=_api_detail(exc)) from exc
        cfg = dict(raw.get("config") or {})
        # Merge live runtime defaults for missing keys
        live = controls.snapshot()
        for key in _CONFIG_KEYS:
            if key not in cfg and key in live:
                cfg[key] = live[key]
            if key == "bot_name" and key not in cfg:
                cfg[key] = memory.bot_name or "Keyholder"
            if key == "domme_title" and key not in cfg:
                cfg[key] = memory.domme_title or ""
        return {
            "ok": True,
            "config": cfg,
            "session_id": raw.get("sessionId"),
            "extension_slug": raw.get("extensionSlug"),
        }

    @api.post("/api/ext/config/save")
    async def ext_config_save(body: ExtConfigSaveBody) -> dict:
        clean = {k: body.config[k] for k in _CONFIG_KEYS if k in body.config}
        try:
            await chaster.put_partner_configuration(
                body.partner_configuration_token, clean
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=401,
                detail=f"Could not save Chaster config: {_api_detail(exc)}",
            ) from exc

        # Sync timings into live runtime controls (no restart)
        ctrl_updates = {
            k: v for k, v in clean.items() if k in controls.snapshot()
        }
        if ctrl_updates:
            controls.update(**ctrl_updates)

        mem_updates = {}
        if "bot_name" in clean and clean["bot_name"]:
            mem_updates["bot_name"] = str(clean["bot_name"]).strip()
        if "domme_title" in clean and clean["domme_title"]:
            mem_updates["domme_title"] = str(clean["domme_title"]).strip()
        if mem_updates:
            memory.update_fields(**mem_updates)

        return {"ok": True, "config": clean}

    def _merged_settings(session_cfg: dict[str, Any]) -> dict[str, Any]:
        """Full config object for Chaster PATCH (replaces whole config)."""
        live = controls.snapshot()
        src = dict(session_cfg or {})
        cfg: dict[str, Any] = {}
        for key in _CONFIG_KEYS:
            if key in src:
                cfg[key] = src[key]
            elif key in live:
                cfg[key] = live[key]
        if "bot_name" not in cfg or not cfg.get("bot_name"):
            cfg["bot_name"] = memory.bot_name or "Keyholder"
        if "domme_title" not in cfg:
            cfg["domme_title"] = memory.domme_title or ""
        # Sensible defaults if still missing (avoids Chaster "Field required")
        cfg.setdefault("auto_punish_enabled", False)
        cfg.setdefault("auto_punish_seconds", 600)
        cfg.setdefault("autopilot_enabled", False)
        cfg.setdefault("autopilot_timezone", "Europe/London")
        cfg.setdefault("autopilot_window_start", "18:00")
        cfg.setdefault("autopilot_window_end", "23:00")
        cfg.setdefault("autopilot_min_minutes", 45)
        cfg.setdefault("autopilot_max_minutes", 120)
        cfg.setdefault("autopilot_allow_chaster", False)
        cfg.setdefault("autopilot_chaster_chance", 0.35)
        cfg.setdefault("autopilot_punish_seconds", 600)
        cfg.setdefault("min_add_time_seconds", 900)
        cfg.setdefault("max_add_time_seconds", 86400)
        cfg.setdefault("soft_add_time_seconds", cfg["min_add_time_seconds"])
        cfg.setdefault("hard_add_time_seconds", cfg["max_add_time_seconds"])
        cfg.setdefault("default_add_time_seconds", cfg["max_add_time_seconds"])
        cfg.setdefault("default_remove_time_seconds", 1800)
        return cfg

    def _sync_controls_from_config(cfg: dict[str, Any]) -> dict[str, Any]:
        """
        Push config into live RuntimeControls (what autopilot actually reads).
        Chaster session config alone does NOT drive the loop — this bridge does.
        """
        updates = {
            k: cfg[k]
            for k in _CONFIG_KEYS
            if k in cfg and k in controls.snapshot()
        }
        if updates:
            return controls.update(**updates)
        return controls.snapshot()

    def _require_keyholder(sess: ExtSession, main_token: str) -> None:
        if sess.role == "keyholder":
            return
        if settings.extension_dev_bypass and main_token.startswith("dev:"):
            return
        raise HTTPException(
            status_code=403,
            detail="Only the keyholder can open session settings.",
        )

    @api.post("/api/ext/settings/get")
    async def ext_settings_get(body: ExtSessionBody) -> dict:
        """Keyholder session settings from the main extension page (mainToken)."""
        sess = await _require_session(chaster, cache, settings, body.main_token)
        _require_keyholder(sess, body.main_token)
        merged = _merged_settings(sess.config)
        # Keep live loop in sync with what the UI shows (survives Render restarts
        # when Chaster still has the saved session config).
        live = _sync_controls_from_config(merged)
        return {
            "ok": True,
            "config": {**merged, **{k: live[k] for k in live if k in _CONFIG_KEYS}},
            "session_id": sess.session_id,
            "autopilot": autopilot_status(settings),
        }

    @api.post("/api/ext/settings/save")
    async def ext_settings_save(request: Request) -> dict:
        """
        Accept raw JSON so we never 422 on Pydantic 'Field required'.
        Supports main_token / mainToken and a missing/partial config object.
        """
        try:
            raw = await request.json()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400, detail="Body must be JSON"
            ) from exc
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="Body must be a JSON object")
        main_token = str(
            raw.get("main_token") or raw.get("mainToken") or ""
        ).strip()
        if len(main_token) < 8:
            raise HTTPException(
                status_code=400,
                detail="main_token missing — reopen the extension from Chaster.",
            )
        cfg_in = raw.get("config")
        if cfg_in is None:
            cfg_in = {}
        if not isinstance(cfg_in, dict):
            raise HTTPException(status_code=400, detail="config must be an object")

        sess = await _require_session(chaster, cache, settings, main_token)
        _require_keyholder(sess, main_token)
        incoming = {k: cfg_in[k] for k in _CONFIG_KEYS if k in cfg_in}
        # Chaster PATCH replaces the WHOLE config object — merge with current
        # session + live controls so required keys are never dropped.
        clean = _merged_settings(sess.config)
        clean.update(incoming)

        # Always persist locally first so the bot uses the new timings even if
        # Chaster session sync fails.
        _sync_controls_from_config(clean)
        mem_updates = {}
        if clean.get("bot_name"):
            mem_updates["bot_name"] = str(clean["bot_name"]).strip()
        if clean.get("domme_title"):
            mem_updates["domme_title"] = str(clean["domme_title"]).strip()
        if mem_updates:
            memory.update_fields(**mem_updates)
        import time as _time

        cache.put(
            ExtSession(
                main_token=sess.main_token,
                role=sess.role,
                user_id=sess.user_id,
                session_id=sess.session_id,
                lock_id=sess.lock_id,
                wearer_username=sess.wearer_username,
                keyholder_username=sess.keyholder_username,
                config=clean,
                fetched_at=_time.time(),
            )
        )

        chaster_sync = "skipped"
        sync_error = ""
        sid = (sess.session_id or "").strip()
        # Lock-extension Mongo _id is 24 hex — partner sessionId looks like "_rV6…".
        # Older code cached the wrong id; recover before PATCH.
        if sid and sid != "dev" and re.fullmatch(r"[a-fA-F0-9]{24}", sid):
            try:
                if sess.lock_id:
                    sid = await chaster.resolve_session_id(sess.lock_id)
            except Exception:  # noqa: BLE001
                pass
        if sid and sid != "dev":
            try:
                await chaster.patch_extension_session(sid, config=clean)
                chaster_sync = "ok"
            except Exception as exc:  # noqa: BLE001
                chaster_sync = "failed"
                sync_error = _api_detail(exc)
                logging.getLogger(__name__).warning(
                    "Settings saved locally; Chaster session sync failed sid=%s: %s",
                    sid,
                    sync_error,
                )

        return {
            "ok": True,
            "config": clean,
            "chaster_sync": chaster_sync,
            "chaster_sync_error": sync_error,
            "autopilot": autopilot_status(settings),
        }

    @api.post("/api/ext/autopilot/tick")
    async def ext_autopilot_tick(body: ExtSessionBody) -> dict:
        """Domme: fire one unprompted group tease immediately (debug / manual)."""
        sess = await _require_session(chaster, cache, settings, body.main_token)
        _require_keyholder(sess, body.main_token)
        posted = await run_unprompted_tick(
            settings=settings,
            agent=agent,
            store=store,
            scene=scene,
            memory=memory,
            bridge=bridge,
            chaster=chaster,
            force=True,
        )
        return {
            "ok": bool(posted),
            "posted": (posted or {}).get("posted") if posted else None,
            "autopilot": autopilot_status(settings),
        }

    @api.post("/api/ext/lockbox/status")
    async def ext_lockbox_status(body: ExtSessionBody) -> dict:
        sess = await _require_session(chaster, cache, settings, body.main_token)
        _require_keyholder(sess, body.main_token)
        if not rad or not rad.configured:
            return {
                "ok": False,
                "configured": False,
                "error": "Set RAD_API_TOKEN on the server",
                "last_sync": last_sync_status(),
            }
        snap = await rad.status_snapshot()
        snap["ok"] = True
        snap["last_sync"] = last_sync_status()
        return snap

    @api.post("/api/ext/lockbox/action")
    async def ext_lockbox_action(body: ExtLockboxBody) -> dict:
        sess = await _require_session(chaster, cache, settings, body.main_token)
        _require_keyholder(sess, body.main_token)
        if not rad or not rad.configured:
            raise HTTPException(
                status_code=503,
                detail="R+D Lockbox not configured (RAD_API_TOKEN)",
            )
        action = (body.action or "").strip().lower()
        if action == "status":
            snap = await rad.status_snapshot()
            snap["ok"] = True
            snap["last_sync"] = last_sync_status()
            return snap
        if action == "unlock":
            result = await unlock_for_hygiene(rad, reason="manual_ext", force=True)
        elif action == "lock":
            result = await relock_after_hygiene(
                rad, chaster, reason="manual_ext", force=True
            )
        elif action == "sync_time":
            result = await sync_duration_from_chaster(
                rad, chaster, reason="manual_ext", force=True
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="action must be lock, unlock, or sync_time",
            )
        snap = await rad.status_snapshot()
        snap["ok"] = bool(result.get("ok"))
        snap["last_sync"] = result
        return snap

    # Denied probe — opening APIs without token
    @api.get("/api/ext/ping")
    async def ext_ping() -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "hint": "UI at /ext — only works with a Chaster mainToken in the hash.",
            }
        )
