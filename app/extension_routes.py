"""Partner-extension HTTP routes: /ext chat + /ext/config settings."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from app.agent import ChatAgent
from app.autopilot import autopilot_status, run_unprompted_tick
from app.bridge import GroupBridge
from app.chaster import ChasterClient
from app.chat_service import handle_chat_turn
from app.play_thread import apply_play_updates, box_button_message
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
from app.persist import save_scene
from app.rad_lockbox import RadLockboxClient, summarize_lockbox
from app.roles import Room, can_access
from app.runtime_controls import RuntimeControls
from app.scene import SceneState
from app.hygiene_request import (
    approve_hygiene,
    deny_hygiene,
    mark_error,
    mark_punished,
    mark_relocked,
    mark_unlocked,
    request_hygiene,
    reset_hygiene,
    should_punish,
    snapshot as hygiene_snapshot,
)
from app.session_kit import load_wearer_catalog
from app.sessions import DisplayMessage, SessionStore
from app.typing_presence import clear_typing, list_typing, set_typing

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
EXT_DIR = STATIC_DIR / "ext"
log = logging.getLogger(__name__)

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
    "hygiene_allowed_seconds",
    "hygiene_late_punish_seconds",
    "bot_allow_add_time",
    "bot_allow_remove_time",
    "bot_allow_freeze",
    "bot_allow_hide_timer",
    "bot_allow_pillory",
    "bot_voice",
    "bot_voice_sample",
    "bot_intensity",
    "bot_quirks",
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


class ExtKitSaveBody(BaseModel):
    main_token: str = Field(min_length=8)
    session_kinks: list[str] = Field(default_factory=list)
    session_toys: list[str] = Field(default_factory=list)


class ExtTypingBody(BaseModel):
    main_token: str = Field(min_length=8)
    room: Room = "group"
    active: bool = True
    label: str = ""


class ExtLockboxBody(BaseModel):
    main_token: str = Field(min_length=8)
    action: str = ""  # lock | unlock | status


class ExtHygieneBody(BaseModel):
    main_token: str = Field(min_length=8)
    action: str = ""  # request | approve | deny | unlock | relock | reset | status
    allowed_seconds: int | None = None


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
    _box_cache: dict[str, Any] = {"at": 0.0, "data": None}

    async def _box_view(*, force: bool = False) -> dict:
        now = time.time()
        cached = _box_cache.get("data")
        if (
            not force
            and cached
            and now - float(_box_cache.get("at") or 0) < 8
        ):
            return cached
        if not rad or not rad.configured:
            view = {
                "configured": False,
                "locked": None,
                "label": "not configured",
                "lock_state": "unknown",
                "active": False,
            }
        else:
            try:
                snap = await rad.status_snapshot()
                view = summarize_lockbox(snap)
            except Exception as exc:  # noqa: BLE001
                log.warning("Lockbox status failed: %s", exc)
                view = {
                    "configured": True,
                    "locked": None,
                    "label": "status error",
                    "error": str(exc)[:160],
                }
        _box_cache["at"] = now
        _box_cache["data"] = view
        return view

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

    def _ext_asset_stamp() -> str:
        newest = 0
        for name in ("index.html", "ext.js", "ext.css"):
            p = EXT_DIR / name
            if p.is_file():
                newest = max(newest, int(p.stat().st_mtime))
        return str(newest or 21)

    def _stamped_ext_html(path: Path) -> HTMLResponse:
        html = path.read_text(encoding="utf-8")
        stamp = _ext_asset_stamp()
        html = html.replace("EXT_BUILD", stamp)
        return HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )

    @api.get("/ext")
    @api.get("/ext/")
    async def ext_main() -> HTMLResponse:
        path = EXT_DIR / "index.html"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Extension UI missing")
        return _stamped_ext_html(path)

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
            "hygiene": await _hygiene_view(),
            "lockbox": await _box_view(),
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
        counts = store.display_counts()
        if sess.app_role != "domme":
            counts = {"group": int(counts.get("group") or 0)}
        return {
            "room": room,
            "role": sess.app_role,
            "chaster_role": sess.role,
            "messages": store.get_display(room),
            "room_counts": counts,
            "typing": list_typing(room, exclude=speaker),
            "hygiene": await _hygiene_view(),
            "lockbox": await _box_view(),
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
        cfg.setdefault("bot_allow_add_time", True)
        cfg.setdefault("bot_allow_remove_time", True)
        cfg.setdefault("bot_allow_freeze", True)
        cfg.setdefault("bot_allow_hide_timer", True)
        cfg.setdefault("bot_allow_pillory", True)
        cfg.setdefault("bot_voice", "cruel")
        cfg.setdefault("bot_voice_sample", "")
        cfg.setdefault("bot_intensity", "firm")
        cfg.setdefault("bot_quirks", "")
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
        snap["lockbox"] = await _box_view(force=True)
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
            snap["lockbox"] = await _box_view(force=True)
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
        snap["lockbox"] = await _box_view(force=True)
        spoken = box_button_message(action)
        if spoken and result.get("ok"):
            apply_play_updates(
                scene,
                {"cage": "off_for_play" if action == "unlock" else "on"},
            )
            try:
                save_scene(scene)
            except Exception:  # noqa: BLE001
                log.exception("Could not save play thread after lockbox %s", action)
            try:
                snap["chat"] = await handle_chat_turn(
                    agent=agent,
                    store=store,
                    scene=scene,
                    memory=memory,
                    bridge=bridge,
                    images=images,
                    chaster=chaster,
                    role="domme",
                    room="private",
                    message=spoken,
                    chaster_role=sess.role,
                    chaster_username=sess.speaker_username,
                )
            except Exception:  # noqa: BLE001
                log.exception("Lockbox %s conversation failed", action)
                snap["chat_error"] = "Box changed; I couldn't start the chat."
        return snap

    def _hygiene_note(text: str, *, room: str = "private") -> None:
        bot = memory.bot_name or "Keyholder"
        if room == "private":
            bridge.inject_private_note(store, text, speaker=bot)
        else:
            store.append_display(
                DisplayMessage(speaker=bot, content=text, room="group", from_bot=True)
            )
        from app.persist import save_sessions

        try:
            save_sessions(store)
        except Exception:  # noqa: BLE001
            log.exception("Could not persist hygiene chat note")

    async def _hygiene_view() -> dict:
        if should_punish():
            secs = max(60, int(getattr(controls, "hygiene_late_punish_seconds", 1800) or 1800))
            try:
                from app.chaster_actions import ChasterIntent, run_chaster_intent

                result = await run_chaster_intent(
                    chaster,
                    ChasterIntent(
                        kind="add_time",
                        seconds=secs,
                        reason="late hygiene relock",
                    ),
                    requested_by="hygiene timer",
                )
                mins = max(1, secs // 60)
                if result.ok and not result.blocked:
                    _hygiene_note(
                        f"He was late relocking. {mins} minutes added.",
                        room="private",
                    )
                    _hygiene_note(
                        f"Late relock — {mins} minutes added.",
                        room="group",
                    )
                else:
                    _hygiene_note(
                        "He was late relocking. Punishment could not be applied — add time?",
                        room="private",
                    )
            except Exception:  # noqa: BLE001
                log.exception("Hygiene late punish failed")
                _hygiene_note(
                    "He was late relocking. Punishment failed — add time?",
                    room="private",
                )
            mark_punished()
        return hygiene_snapshot()

    @api.post("/api/ext/hygiene")
    async def ext_hygiene(body: ExtHygieneBody) -> dict:
        sess = await _require_session(chaster, cache, settings, body.main_token)
        action = (body.action or "status").strip().lower()
        default_allowed = max(
            60, int(getattr(controls, "hygiene_allowed_seconds", 600) or 600)
        )
        chosen = body.allowed_seconds
        allowed = max(60, int(chosen or default_allowed))
        is_kh = sess.role == "keyholder" or sess.app_role == "domme"
        is_sub = sess.role == "wearer" or sess.app_role == "sub"

        if action == "status":
            return {"ok": True, "hygiene": await _hygiene_view()}

        if action == "request":
            if is_kh and not is_sub:
                raise HTTPException(status_code=403, detail="The lockee requests hygiene.")
            view = request_hygiene(allowed_seconds=default_allowed)
            if view.get("status") == "requested":
                _hygiene_note(
                    "Lockee requested hygiene. How long may he be unlocked? "
                    "Approve with a time (e.g. 15) or Deny. He cannot see this yet.",
                    room="private",
                )
            return {"ok": True, "hygiene": view}

        if action == "approve":
            if not is_kh:
                raise HTTPException(status_code=403, detail="Only the keyholder can approve.")
            try:
                view = approve_hygiene(allowed_seconds=allowed)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            mins = max(1, int(view.get("allowed_seconds") or allowed) // 60)
            _hygiene_note(
                f"You approved {mins} min. He cannot see the bargaining — "
                "I told him Unlock is next to Group.",
                room="private",
            )
            _hygiene_note(
                "Unlock is next to Group. Lock before time's up or there will be a consequence.",
                room="group",
            )
            return {"ok": True, "hygiene": view}

        if action == "deny":
            if not is_kh:
                raise HTTPException(status_code=403, detail="Only the keyholder can deny.")
            view = deny_hygiene()
            _hygiene_note("You denied hygiene. He may request again.", room="private")
            _hygiene_note("Hygiene denied. You may request again.", room="group")
            return {"ok": True, "hygiene": view}

        if action == "reset":
            if not is_kh:
                raise HTTPException(status_code=403, detail="Only the keyholder can reset.")
            view = reset_hygiene()
            _hygiene_note("Hygiene reset. He may request again.", room="private")
            return {"ok": True, "hygiene": view}

        if action == "unlock":
            if not is_sub:
                raise HTTPException(
                    status_code=403,
                    detail="After approval, the lockee unlocks.",
                )
            if not rad or not rad.configured:
                raise HTTPException(
                    status_code=503,
                    detail="R+D Lockbox not configured (RAD_API_TOKEN)",
                )
            try:
                view = mark_unlocked(allowed_seconds=0)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            result = await unlock_for_hygiene(rad, reason="hygiene_request", force=True)
            if not result.get("ok"):
                reset_hygiene()
                mark_error(str(result.get("detail") or "unlock failed"))
                raise HTTPException(
                    status_code=502,
                    detail=result.get("detail") or "Could not unlock the box",
                )
            mins = max(1, int(view.get("allowed_seconds") or 600) // 60)
            _hygiene_note(
                f"Unlocked. Tap Lock next to Group before {mins} min is up.",
                room="group",
            )
            return {
                "ok": True,
                "hygiene": view,
                "lockbox": await _box_view(force=True),
            }

        if action == "relock":
            if not is_sub and not is_kh:
                raise HTTPException(status_code=403, detail="Relock is for the lockee.")
            if not rad or not rad.configured:
                raise HTTPException(
                    status_code=503,
                    detail="R+D Lockbox not configured (RAD_API_TOKEN)",
                )
            await _hygiene_view()
            result = await relock_after_hygiene(
                rad, chaster, reason="hygiene_request", force=True
            )
            if not result.get("ok"):
                mark_error(str(result.get("detail") or "relock failed"))
                raise HTTPException(
                    status_code=502,
                    detail=result.get("detail") or "Could not relock the box",
                )
            late = hygiene_snapshot().get("punished")
            mark_relocked()
            _hygiene_note(
                "Hygiene relocked. Late — punishment already applied."
                if late
                else "Hygiene relocked on time.",
                room="group",
            )
            return {
                "ok": True,
                "hygiene": hygiene_snapshot(),
                "lockbox": await _box_view(force=True),
            }

        raise HTTPException(
            status_code=400,
            detail="action must be request, approve, deny, reset, unlock, relock, or status",
        )

    @api.post("/api/ext/kink-catalog")
    async def ext_kink_catalog(body: ExtSessionBody) -> dict:
        """Keyholder: wearer kinks/toys for the session-kit picker."""
        sess = await _require_session(chaster, cache, settings, body.main_token)
        _require_keyholder(sess, body.main_token)
        catalog = await load_wearer_catalog(
            chaster=chaster,
            memory=memory,
            scene=scene,
            username_hint=sess.wearer_username or "",
        )
        return catalog

    @api.post("/api/ext/session-kit")
    async def ext_session_kit_save(body: ExtKitSaveBody) -> dict:
        sess = await _require_session(chaster, cache, settings, body.main_token)
        _require_keyholder(sess, body.main_token)
        updated = scene.update(
            session_kinks=body.session_kinks,
            session_toys=body.session_toys,
        )
        save_scene(scene)
        return {
            "ok": True,
            "session_kinks": updated.get("session_kinks") or [],
            "session_toys": updated.get("session_toys") or [],
        }

    # Denied probe — opening APIs without token
    @api.get("/api/ext/ping")
    async def ext_ping() -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "hint": "UI at /ext — only works with a Chaster mainToken in the hash.",
            }
        )
