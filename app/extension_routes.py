"""Partner-extension HTTP routes: /ext chat + /ext/config settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.agent import ChatAgent
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
from app.memory import LongTermMemory
from app.roles import Room, can_access
from app.runtime_controls import RuntimeControls
from app.scene import SceneState
from app.sessions import SessionStore

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
        return response

    @api.get("/ext")
    @api.get("/ext/")
    async def ext_main() -> FileResponse:
        path = EXT_DIR / "index.html"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Extension UI missing")
        return FileResponse(path)

    @api.get("/ext/config")
    @api.get("/ext/config/")
    async def ext_config_page() -> FileResponse:
        path = EXT_DIR / "config.html"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Config UI missing")
        return FileResponse(path)

    @api.post("/api/ext/session")
    async def ext_session(body: ExtSessionBody) -> dict:
        sess = await _require_session(chaster, cache, settings, body.main_token)
        return {
            "ok": True,
            "session": public_session_view(sess),
            "bot_name": memory.bot_name or "Keyholder",
            "domme_title": memory.domme_title or "Mistress",
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
        return {
            "room": room,
            "role": sess.app_role,
            "chaster_role": sess.role,
            "messages": store.get_display(room),
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
                cfg[key] = memory.domme_title or "Mistress"
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
        cfg = dict(session_cfg or {})
        live = controls.snapshot()
        for key in _CONFIG_KEYS:
            if key not in cfg and key in live:
                cfg[key] = live[key]
        if "bot_name" not in cfg:
            cfg["bot_name"] = memory.bot_name or "Keyholder"
        if "domme_title" not in cfg:
            cfg["domme_title"] = memory.domme_title or "Mistress"
        return cfg

    class ExtSettingsSaveBody(BaseModel):
        main_token: str = Field(min_length=8)
        config: dict[str, Any]

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
        return {
            "ok": True,
            "config": _merged_settings(sess.config),
            "session_id": sess.session_id,
        }

    @api.post("/api/ext/settings/save")
    async def ext_settings_save(body: ExtSettingsSaveBody) -> dict:
        sess = await _require_session(chaster, cache, settings, body.main_token)
        _require_keyholder(sess, body.main_token)
        clean = {k: body.config[k] for k in _CONFIG_KEYS if k in body.config}
        if sess.session_id and sess.session_id != "dev":
            try:
                await chaster.patch_extension_session(sess.session_id, config=clean)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=502,
                    detail=f"Could not save session config: {_api_detail(exc)}",
                ) from exc
        ctrl_updates = {k: v for k, v in clean.items() if k in controls.snapshot()}
        if ctrl_updates:
            controls.update(**ctrl_updates)
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
                config={**sess.config, **clean},
                fetched_at=_time.time(),
            )
        )
        return {"ok": True, "config": clean}

    # Denied probe — opening APIs without token
    @api.get("/api/ext/ping")
    async def ext_ping() -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "hint": "UI at /ext — only works with a Chaster mainToken in the hash.",
            }
        )
