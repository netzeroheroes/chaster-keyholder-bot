from __future__ import annotations

import argparse
import logging
import threading

import uvicorn

from app.agent import ChatAgent
from app.api import create_api
from app.bridge import GroupBridge
from app.chaster import ChasterClient
from app.config import get_settings
from app.images import ImageService
from app.memory import LongTermMemory
from app.persist import load_scene, load_sessions
from app.rad_lockbox import init_rad_client
from app.sessions import SessionStore
from app.telegram_bot import build_telegram_app
from app.tools import build_default_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("chatbot")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI chatbot (HTTP + optional Telegram)")
    parser.add_argument(
        "--http-only",
        action="store_true",
        help="Do not start Telegram even if TELEGRAM_BOT_TOKEN is set",
    )
    parser.add_argument(
        "--telegram-only",
        action="store_true",
        help="Run Telegram polling without the HTTP API",
    )
    args = parser.parse_args()

    settings = get_settings()
    tools = build_default_registry()
    agent = ChatAgent(settings, tools)
    store = SessionStore()
    load_sessions(store)
    scene = load_scene()
    memory = LongTermMemory.load()
    bridge = GroupBridge()
    images = ImageService(settings)
    chaster = ChasterClient(settings)
    rad = init_rad_client(settings)

    run_http = not args.telegram_only
    run_telegram = bool(settings.telegram_bot_token.strip()) and not args.http_only

    if not run_http and not run_telegram:
        raise SystemExit(
            "Nothing to run. Set TELEGRAM_BOT_TOKEN or omit --telegram-only."
        )

    log.info(
        "LLM: model=%s base_url=%s",
        settings.llm_model,
        settings.llm_base_url,
    )
    log.info(
        "Memory: Domme=%s title=%s Sub=%s",
        memory.domme_name or "?",
        memory.domme_title,
        memory.sub_name or "?",
    )
    log.info(
        "Images: enabled=%s model=%s",
        images.enabled,
        settings.image_model,
    )
    log.info("Chaster: configured=%s", chaster.configured)
    log.info(
        "R+D Lockbox: configured=%s sync=%s hygiene=%s template=%s",
        rad.configured,
        settings.rad_lockbox_sync_enabled,
        settings.rad_sync_hygiene,
        settings.rad_lock_settings_id or "?",
    )
    log.info(
        "Auto-punish=%s Autopilot=%s window=%s-%s %s",
        settings.auto_punish_enabled,
        settings.autopilot_enabled,
        settings.autopilot_window_start,
        settings.autopilot_window_end,
        settings.autopilot_timezone,
    )

    if run_telegram and run_http:
        def _serve_http() -> None:
            api = create_api(
                agent,
                store,
                scene,
                settings,
                bridge,
                memory,
                images,
                chaster,
                rad=rad,
            )
            uvicorn.run(api, host=settings.host, port=settings.port, log_level="info")

        thread = threading.Thread(target=_serve_http, name="http-api", daemon=True)
        thread.start()
        log.info("HTTP API on http://%s:%s", settings.host, settings.port)

        tg = build_telegram_app(
            settings.telegram_bot_token,
            agent,
            store,
            scene,
            settings,
            bridge,
            memory,
        )
        log.info("Starting Telegram bot polling…")
        tg.run_polling(allowed_updates=["message"])
        return

    if run_telegram:
        tg = build_telegram_app(
            settings.telegram_bot_token,
            agent,
            store,
            scene,
            settings,
            bridge,
            memory,
        )
        log.info("Starting Telegram bot polling…")
        tg.run_polling(allowed_updates=["message"])
        return

    api = create_api(
        agent, store, scene, settings, bridge, memory, images, chaster, rad=rad
    )
    uvicorn.run(api, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
