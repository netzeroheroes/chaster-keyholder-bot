from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.autopilot import autopilot_loop, in_window
from app.extension_routes import register_extension_routes
from app.runtime_controls import init_controls

from app.agent import ChatAgent
from app.bridge import GroupBridge
from app.chaster import ChasterClient
from app.chat_service import handle_chat_turn
from app.config import Settings
from app.images import IMAGES_DIR, ImageService
from app.memory import LongTermMemory
from app.persist import save_scene, save_sessions
from app.roles import Room, Role, can_access
from app.scene import SceneState
from app.sessions import DisplayMessage, SessionStore

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    role: Role
    room: Room = "group"
    pin: str = ""


class ChatResponse(BaseModel):
    reply: str
    room: Room
    role: Role
    group_posts: list[str] = []
    image_urls: list[str] = []


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=3)
    role: Role = "domme"
    pin: str = ""
    room: Room = "group"
    post_to_room: bool = True


class ResetRequest(BaseModel):
    room: Room
    role: Role
    pin: str = ""


class SceneUpdate(BaseModel):
    role: Role = "domme"
    pin: str = ""
    private_prompt: str | None = None
    group_prompt: str | None = None
    secret_directives: str | None = None


class AuthRequest(BaseModel):
    role: Role
    pin: str = ""


class GroupSayRequest(BaseModel):
    message: str = Field(min_length=1)
    role: Role = "domme"
    pin: str = ""


class MemoryUpdate(BaseModel):
    role: Role = "domme"
    pin: str = ""
    domme_name: str | None = None
    domme_title: str | None = None
    bot_name: str | None = None
    sub_name: str | None = None
    sub_titles: list[str] | None = None
    hard_limits: list[str] | None = None
    soft_limits: list[str] | None = None
    kinks: list[str] | None = None
    chastity: dict[str, str] | None = None
    relationship_notes: list[str] | None = None
    timeline: list[str] | None = None
    private_bond: list[str] | None = None


class ChasterTimeRequest(BaseModel):
    role: Role = "domme"
    pin: str = ""
    lock_id: str = ""
    seconds: int = Field(..., description="Positive adds time, negative removes")


class ChasterFreezeRequest(BaseModel):
    role: Role = "domme"
    pin: str = ""
    lock_id: str = ""
    frozen: bool = True


class ChasterPilloryRequest(BaseModel):
    role: Role = "domme"
    pin: str = ""
    lock_id: str = ""
    seconds: int = Field(default=300, ge=300, le=86400)
    reason: str = "AI Domme punishment"


class ChasterDisplayTimeRequest(BaseModel):
    role: Role = "domme"
    pin: str = ""
    lock_id: str = ""
    display: bool = True


class ControlsUpdate(BaseModel):
    role: Role = "domme"
    pin: str = ""
    auto_punish_enabled: bool | None = None
    auto_punish_seconds: int | None = Field(default=None, ge=60, le=86400)
    autopilot_enabled: bool | None = None
    autopilot_timezone: str | None = None
    autopilot_window_start: str | None = None
    autopilot_window_end: str | None = None
    autopilot_min_minutes: int | None = Field(default=None, ge=5, le=720)
    autopilot_max_minutes: int | None = Field(default=None, ge=5, le=1440)
    autopilot_allow_chaster: bool | None = None
    autopilot_chaster_chance: float | None = Field(default=None, ge=0.0, le=1.0)
    autopilot_punish_seconds: int | None = Field(default=None, ge=60, le=86400)


def create_api(
    agent: ChatAgent,
    store: SessionStore,
    scene: SceneState,
    settings: Settings,
    bridge: GroupBridge,
    memory: LongTermMemory,
    images: ImageService,
    chaster: ChasterClient,
) -> FastAPI:
    controls = init_controls(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Always run the loop; it no-ops when autopilot_enabled is false
        task = asyncio.create_task(
            autopilot_loop(
                settings=settings,
                agent=agent,
                store=store,
                scene=scene,
                memory=memory,
                bridge=bridge,
                chaster=chaster,
            ),
            name="autopilot",
        )
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    api = FastAPI(title="Chatbot", version="0.7.0", lifespan=lifespan)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    api.mount("/media/images", StaticFiles(directory=IMAGES_DIR), name="media-images")
    oauth_states: set[str] = set()

    @api.middleware("http")
    async def collapse_double_slashes(request: Request, call_next):
        # Chaster Extension URLs often end up as ...com//ext when a trailing slash is pasted
        path = request.url.path or "/"
        if "//" in path:
            cleaned = re.sub(r"/{2,}", "/", path)
            if cleaned != path:
                target = cleaned
                if request.url.query:
                    target = f"{cleaned}?{request.url.query}"
                return RedirectResponse(url=target, status_code=308)
        return await call_next(request)

    def _check_pin(role: Role, pin: str) -> None:
        expected = settings.domme_pin if role == "domme" else settings.sub_pin
        if expected and pin != expected:
            raise HTTPException(status_code=401, detail="Invalid PIN for this role")

    @api.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/api/meta")
    async def meta() -> dict:
        return {
            "model": settings.llm_model,
            "image_enabled": images.enabled,
            "image_model": settings.image_model,
            "chaster_configured": chaster.configured,
            "auto_punish_enabled": controls.auto_punish_enabled,
            "autopilot": {
                **controls.snapshot(),
                "in_window": in_window(settings),
            },
            "pins_required": {
                "domme": bool(settings.domme_pin),
                "sub": bool(settings.sub_pin),
            },
        }

    @api.get("/api/controls")
    async def get_controls_api(
        role: Role = "domme",
        x_role_pin: str = Header(default=""),
    ) -> dict:
        if role != "domme":
            raise HTTPException(status_code=403, detail="Domme only")
        _check_pin(role, x_role_pin)
        return {**controls.snapshot(), "in_window": in_window(settings)}

    @api.patch("/api/controls")
    async def patch_controls(body: ControlsUpdate) -> dict:
        if body.role != "domme":
            raise HTTPException(status_code=403, detail="Domme only")
        _check_pin(body.role, body.pin)
        updates = body.model_dump(exclude={"role", "pin"}, exclude_none=True)
        snap = controls.update(**updates)
        return {**snap, "in_window": in_window(settings)}

    @api.get("/api/chaster/status")
    async def chaster_status(
        role: Role = "domme",
        x_role_pin: str = Header(default=""),
    ) -> dict:
        if role != "domme":
            raise HTTPException(status_code=403, detail="Domme only")
        _check_pin(role, x_role_pin)
        return await chaster.status()

    @api.get("/api/chaster/login")
    async def chaster_login() -> RedirectResponse:
        if not settings.chaster_client_id or not settings.chaster_client_secret:
            raise HTTPException(status_code=503, detail="Chaster client credentials missing")
        url, state = chaster.authorization_url()
        oauth_states.add(state)
        return RedirectResponse(url)

    @api.get("/api/chaster/callback")
    async def chaster_callback(
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> HTMLResponse:
        if error:
            return HTMLResponse(
                f"<h1>Chaster login failed</h1><p>{error}</p>",
                status_code=400,
            )
        if not code or not state or state not in oauth_states:
            return HTMLResponse(
                "<h1>Invalid Chaster callback</h1><p>Missing/invalid state. Try login again.</p>",
                status_code=400,
            )
        oauth_states.discard(state)
        try:
            await chaster.exchange_code(code)
        except Exception as exc:  # noqa: BLE001
            return HTMLResponse(
                f"<h1>Token exchange failed</h1><pre>{exc}</pre>",
                status_code=502,
            )
        return HTMLResponse(
            "<h1>Chaster linked</h1>"
            "<p>You can close this tab and return to Chat Lab.</p>"
            "<script>setTimeout(()=>window.close(), 1500)</script>"
        )

    @api.get("/api/chaster/wearers")
    async def chaster_wearers(
        role: Role = "domme",
        x_role_pin: str = Header(default=""),
        status: str = Query(default="locked"),
    ) -> dict:
        if role != "domme":
            raise HTTPException(status_code=403, detail="Domme only")
        _check_pin(role, x_role_pin)
        try:
            raw = await chaster.search_wearers(status=status)
            own = await chaster.list_own_locks()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        keyholder_locks = chaster.summarize_locks(raw or {})
        own_locks = chaster.summarize_locks(own)
        # Prefer keyholder wearers; fall back to locks on this token (test / self locks)
        locks = keyholder_locks or own_locks
        return {
            "locks": locks,
            "keyholder_locks": keyholder_locks,
            "own_locks": own_locks,
            "raw_total": (raw or {}).get("total"),
        }

    @api.post("/api/chaster/time")
    async def chaster_time(body: ChasterTimeRequest) -> dict:
        if body.role != "domme":
            raise HTTPException(status_code=403, detail="Domme only")
        _check_pin(body.role, body.pin)
        lock_id = body.lock_id or settings.chaster_lock_id
        if not lock_id:
            raise HTTPException(status_code=400, detail="lock_id required (or set CHASTER_LOCK_ID)")
        try:
            await chaster.update_time(lock_id, body.seconds)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"status": "ok", "lock_id": lock_id, "seconds": body.seconds}

    @api.post("/api/chaster/freeze")
    async def chaster_freeze(body: ChasterFreezeRequest) -> dict:
        if body.role != "domme":
            raise HTTPException(status_code=403, detail="Domme only")
        _check_pin(body.role, body.pin)
        lock_id = body.lock_id or settings.chaster_lock_id
        if not lock_id:
            raise HTTPException(status_code=400, detail="lock_id required (or set CHASTER_LOCK_ID)")
        try:
            await chaster.set_freeze(lock_id, body.frozen)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"status": "ok", "lock_id": lock_id, "frozen": body.frozen}

    @api.post("/api/chaster/pillory")
    async def chaster_pillory(body: ChasterPilloryRequest) -> dict:
        if body.role != "domme":
            raise HTTPException(status_code=403, detail="Domme only")
        _check_pin(body.role, body.pin)
        lock_id = body.lock_id or settings.chaster_lock_id
        if not lock_id:
            raise HTTPException(status_code=400, detail="lock_id required (or set CHASTER_LOCK_ID)")
        try:
            await chaster.pillory(lock_id, duration_seconds=body.seconds, reason=body.reason)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "status": "ok",
            "lock_id": lock_id,
            "seconds": body.seconds,
            "reason": body.reason,
        }

    @api.post("/api/chaster/display-time")
    async def chaster_display_time(body: ChasterDisplayTimeRequest) -> dict:
        if body.role != "domme":
            raise HTTPException(status_code=403, detail="Domme only")
        _check_pin(body.role, body.pin)
        lock_id = body.lock_id or settings.chaster_lock_id
        if not lock_id:
            raise HTTPException(status_code=400, detail="lock_id required (or set CHASTER_LOCK_ID)")
        try:
            await chaster.set_display_remaining_time(lock_id, body.display)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"status": "ok", "lock_id": lock_id, "display": body.display}

    @api.post("/api/image")
    async def generate_image(body: ImageRequest) -> dict:
        if body.role != "domme":
            raise HTTPException(status_code=403, detail="Only the Domme can generate images")
        _check_pin(body.role, body.pin)
        if not images.enabled:
            raise HTTPException(status_code=503, detail="Image generation disabled")
        try:
            result = await images.generate(body.prompt)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        if body.post_to_room:
            store.append_display(
                DisplayMessage(
                    speaker=(memory.bot_name or "Keyholder").strip() or "Keyholder",
                    content=f"[image] {body.prompt}",
                    room=body.room,
                    image_url=result["url"],
                )
            )
            save_sessions(store)
        return result

    @api.post("/api/auth")
    async def auth(body: AuthRequest) -> dict[str, str]:
        _check_pin(body.role, body.pin)
        return {"status": "ok", "role": body.role}

    @api.get("/api/scene")
    async def get_scene(
        role: Role = "domme",
        x_role_pin: str = Header(default=""),
    ) -> dict:
        _check_pin(role, x_role_pin)
        snap = scene.snapshot()
        if role != "domme":
            return {
                "group_prompt": snap["group_prompt"],
                "secret_directives": None,
                "private_prompt": None,
            }
        return snap

    @api.put("/api/scene")
    async def update_scene(body: SceneUpdate) -> dict:
        if body.role != "domme":
            raise HTTPException(status_code=403, detail="Only the Domme can edit the scene")
        _check_pin(body.role, body.pin)
        updated = scene.update(
            private_prompt=body.private_prompt,
            group_prompt=body.group_prompt,
            secret_directives=body.secret_directives,
        )
        save_scene(scene)
        return updated

    @api.get("/api/memory")
    async def get_memory(
        role: Role = "domme",
        x_role_pin: str = Header(default=""),
    ) -> dict:
        _check_pin(role, x_role_pin)
        snap = memory.snapshot()
        if role != "domme":
            # Sub can know shared facts, not private bond notes
            return {
                "domme_name": snap["domme_name"],
                "domme_title": snap["domme_title"],
                "sub_name": snap["sub_name"],
                "sub_titles": snap["sub_titles"],
                "hard_limits": snap["hard_limits"],
                "kinks": snap["kinks"],
                "chastity": snap["chastity"],
                "private_bond": None,
                "relationship_notes": snap["relationship_notes"][-6:],
                "timeline": snap["timeline"][-8:],
            }
        return snap

    @api.put("/api/memory")
    async def update_memory(body: MemoryUpdate) -> dict:
        if body.role != "domme":
            raise HTTPException(status_code=403, detail="Only the Domme can edit memory")
        _check_pin(body.role, body.pin)
        updates = body.model_dump(exclude={"role", "pin"}, exclude_none=True)
        return memory.update_fields(**updates)

    @api.get("/api/history/{room}")
    async def history(
        room: Room,
        role: Role = "domme",
        x_role_pin: str = Header(default=""),
    ) -> dict:
        _check_pin(role, x_role_pin)
        if not can_access(role, room):
            raise HTTPException(status_code=403, detail="Sub cannot access Domme private chat")
        return {"room": room, "messages": store.get_display(room)}

    @api.post("/api/group/say")
    async def group_say(body: GroupSayRequest) -> dict:
        if body.role != "domme":
            raise HTTPException(status_code=403, detail="Only the Domme can force group lines")
        _check_pin(body.role, body.pin)
        posted = await bridge.publish_group_messages(store, [body.message.strip()])
        save_sessions(store)
        return {"status": "ok", "group_posts": posted}

    @api.post("/chat", response_model=ChatResponse)
    async def chat(body: ChatRequest) -> ChatResponse:
        _check_pin(body.role, body.pin)
        if not can_access(body.role, body.room):
            raise HTTPException(status_code=403, detail="Sub cannot access Domme private chat")
        try:
            result = await handle_chat_turn(
                agent=agent,
                store=store,
                scene=scene,
                memory=memory,
                bridge=bridge,
                images=images,
                chaster=chaster,
                role=body.role,
                room=body.room,
                message=body.message,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return ChatResponse(**result)

    @api.post("/reset")
    async def reset(body: ResetRequest) -> dict[str, str]:
        _check_pin(body.role, body.pin)
        if body.role != "domme":
            raise HTTPException(status_code=403, detail="Only the Domme can reset rooms")
        if not can_access(body.role, body.room):
            raise HTTPException(status_code=403, detail="Forbidden")
        store.clear_room(body.room)
        save_sessions(store)
        return {"status": "cleared", "room": body.room}

    register_extension_routes(
        api,
        settings=settings,
        agent=agent,
        store=store,
        scene=scene,
        memory=memory,
        bridge=bridge,
        images=images,
        chaster=chaster,
        controls=controls,
    )

    if STATIC_DIR.is_dir():
        api.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @api.get("/", response_model=None)
        async def index():
            # Chaster Main page URL is often set to the site root — send them to /ext
            if not settings.standalone_ui_enabled:
                return RedirectResponse(url="/ext", status_code=302)
            return FileResponse(STATIC_DIR / "index.html")

        @api.get("/main", response_model=None)
        @api.get("/extension", response_model=None)
        async def ext_aliases():
            return RedirectResponse(url="/ext", status_code=302)

    @api.exception_handler(404)
    async def not_found_handler(request, exc):  # noqa: ARG001
        # Browser / iframe: point people at the real Chaster entrypoints
        accept = (request.headers.get("accept") or "").lower()
        if "text/html" in accept or request.url.path in ("/", "/ext", "/ext/"):
            return HTMLResponse(
                "<!doctype html><meta charset=utf-8>"
                "<title>Not found</title>"
                "<body style='font-family:system-ui;background:#14110f;color:#f3e9e0;"
                "display:grid;place-items:center;min-height:100vh;margin:0;padding:1rem;"
                "text-align:center'>"
                "<div><p><strong>Not found</strong></p>"
                "<p style='color:#9a8b7e'>Chaster Main page URL must be "
                "<code style='color:#e08763'>/ext</code><br/>"
                "Config page URL must be "
                "<code style='color:#e08763'>/ext/config</code></p>"
                "<p><a href='/ext' style='color:#e08763'>Open /ext</a> · "
                "<a href='/ext/config' style='color:#e08763'>Open /ext/config</a> · "
                "<a href='/health' style='color:#e08763'>/health</a></p></div></body>",
                status_code=404,
            )
        return JSONResponse({"detail": "Not Found", "try": ["/ext", "/ext/config", "/health"]}, status_code=404)

    return api
