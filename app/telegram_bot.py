from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.agent import ChatAgent
from app.bridge import GroupBridge
from app.chat_service import handle_chat_turn
from app.config import Settings
from app.memory import LongTermMemory
from app.persist import save_sessions
from app.scene import SceneState
from app.sessions import SessionStore

log = logging.getLogger(__name__)


def _role_for(user_id: int, settings: Settings) -> str | None:
    if settings.telegram_domme_user_id and user_id == settings.telegram_domme_user_id:
        return "domme"
    if settings.telegram_sub_user_id and user_id == settings.telegram_sub_user_id:
        return "sub"
    return None


def _remember_group_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not settings.telegram_group_chat_id:
        settings.telegram_group_chat_id = chat_id
        log.info("Remembered Telegram group chat id=%s", chat_id)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    settings: Settings = context.application.bot_data["settings"]
    memory: LongTermMemory = context.application.bot_data["memory"]
    role = _role_for(update.effective_user.id, settings)
    title = memory.domme_title or "Mistress"
    if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE:
        if role == "domme":
            await update.message.reply_text(
                f"Private = PLANNING with you, {title}.\n"
                "I remember our history and grow with you over time.\n"
                "Group = EXECUTION with you and the Sub — I'll always acknowledge you there.\n"
                "Commands:\n"
                "/group <text> — post exact text into group\n"
                "/direct <text> — set active plan\n"
                "/memory — show long-term memory\n"
                "/reset_private — clear planning chat memory\n"
                "/reset_group — clear execution chat memory"
            )
        elif role == "sub":
            await update.message.reply_text(
                "You're the Sub. Use the shared group chat — private DM is Domme-only."
            )
        else:
            await update.message.reply_text(
                "Your Telegram user id is not configured.\n"
                f"Your id: {update.effective_user.id}"
            )
    else:
        if update.effective_chat:
            _remember_group_chat(context, update.effective_chat.id)
        await update.message.reply_text(
            f"Group = execution. I work with {title} and the Sub, and I remember our arc."
        )


async def memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    settings: Settings = context.application.bot_data["settings"]
    if _role_for(update.effective_user.id, settings) != "domme":
        await update.message.reply_text("Only the Domme can view full memory.")
        return
    memory: LongTermMemory = context.application.bot_data["memory"]
    snap = memory.snapshot()
    text = (
        f"Domme: {snap['domme_name'] or '?'} ({snap['domme_title']})\n"
        f"Sub: {snap['sub_name'] or '?'}\n"
        f"Hard limits: {', '.join(snap['hard_limits']) or '—'}\n"
        f"Kinks: {', '.join(snap['kinks']) or '—'}\n"
        f"Chastity: {snap['chastity'] or '—'}\n"
        f"Timeline:\n- " + "\n- ".join(snap["timeline"][-8:] or ["(empty)"])
    )
    await update.message.reply_text(text[:4000])


async def directives_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    settings: Settings = context.application.bot_data["settings"]
    if _role_for(update.effective_user.id, settings) != "domme":
        await update.message.reply_text("Only the Domme can view the plan.")
        return
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Use /directives in our private chat.")
        return
    scene: SceneState = context.application.bot_data["scene"]
    await update.message.reply_text(
        "Active plan:\n" + (scene.secret_directives or "(none)")
    )


async def direct_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    settings: Settings = context.application.bot_data["settings"]
    if _role_for(update.effective_user.id, settings) != "domme":
        await update.message.reply_text("Only the Domme can set the plan.")
        return
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Set the plan in our private chat.")
        return
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /direct <active plan text>")
        return
    scene: SceneState = context.application.bot_data["scene"]
    from app.persist import save_scene

    scene.update(secret_directives=text)
    save_scene(scene)
    await update.message.reply_text("Active plan updated.")


async def group_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    settings: Settings = context.application.bot_data["settings"]
    if _role_for(update.effective_user.id, settings) != "domme":
        await update.message.reply_text("Only the Domme can force group lines.")
        return
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Use /group in our private chat.")
        return
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /group Kneel for Mistress.")
        return
    bridge: GroupBridge = context.application.bot_data["bridge"]
    store: SessionStore = context.application.bot_data["store"]
    await bridge.publish_group_messages(store, [text])
    save_sessions(store)
    await update.message.reply_text("Posted to group.")


async def reset_private_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    settings: Settings = context.application.bot_data["settings"]
    if _role_for(update.effective_user.id, settings) != "domme":
        return
    store: SessionStore = context.application.bot_data["store"]
    store.clear_room("private")
    save_sessions(store)
    await update.message.reply_text(
        "Planning chat cleared. Long-term memory is kept."
    )


async def reset_group_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    settings: Settings = context.application.bot_data["settings"]
    if _role_for(update.effective_user.id, settings) != "domme":
        await update.message.reply_text("Only the Domme can reset the group.")
        return
    store: SessionStore = context.application.bot_data["store"]
    store.clear_room("group")
    save_sessions(store)
    await update.message.reply_text(
        "Execution chat cleared. Long-term memory is kept."
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not update.effective_user:
        return

    settings: Settings = context.application.bot_data["settings"]
    agent: ChatAgent = context.application.bot_data["agent"]
    store: SessionStore = context.application.bot_data["store"]
    scene: SceneState = context.application.bot_data["scene"]
    bridge: GroupBridge = context.application.bot_data["bridge"]
    memory: LongTermMemory = context.application.bot_data["memory"]

    role = _role_for(update.effective_user.id, settings)
    if role is None:
        if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE:
            await update.message.reply_text(
                f"Unknown user. Your Telegram id is {update.effective_user.id}."
            )
        return

    chat = update.effective_chat
    assert chat is not None

    if chat.type == ChatType.PRIVATE:
        if role != "domme":
            await update.message.reply_text(
                "Private chat is Domme-only. Use the group chat."
            )
            return
        room = "private"
    else:
        _remember_group_chat(context, chat.id)
        if settings.telegram_group_chat_id and chat.id != settings.telegram_group_chat_id:
            return
        room = "group"

    await chat.send_action("typing")
    try:
        result = await handle_chat_turn(
            agent=agent,
            store=store,
            scene=scene,
            memory=memory,
            bridge=bridge,
            role=role,  # type: ignore[arg-type]
            room=room,  # type: ignore[arg-type]
            message=update.message.text,
        )
    except Exception:
        log.exception("Telegram reply failed room=%s", room)
        await update.message.reply_text("Model error — check server logs.")
        return

    beats = [str(b).strip() for b in (result.get("replies") or []) if str(b).strip()]
    if not beats:
        text = str(result.get("reply") or "").strip()
        beats = [text] if text else []
    for i, beat in enumerate(beats):
        if i:
            await chat.send_action("typing")
            await asyncio.sleep(0.45)
        text = beat if len(beat) <= 4000 else beat[:3990] + "\n…"
        await update.message.reply_text(text)


def build_telegram_app(
    token: str,
    agent: ChatAgent,
    store: SessionStore,
    scene: SceneState,
    settings: Settings,
    bridge: GroupBridge,
    memory: LongTermMemory,
) -> Application:
    app = Application.builder().token(token).build()
    app.bot_data["agent"] = agent
    app.bot_data["store"] = store
    app.bot_data["scene"] = scene
    app.bot_data["settings"] = settings
    app.bot_data["bridge"] = bridge
    app.bot_data["memory"] = memory

    async def _telegram_group_send(text: str) -> None:
        chat_id = settings.telegram_group_chat_id
        if not chat_id:
            log.warning("No TELEGRAM_GROUP_CHAT_ID set; cannot push to Telegram group")
            return
        await app.bot.send_message(chat_id=chat_id, text=text)

    bridge.set_telegram_sender(_telegram_group_send)

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("group", group_cmd))
    app.add_handler(CommandHandler("direct", direct_cmd))
    app.add_handler(CommandHandler("directives", directives_cmd))
    app.add_handler(CommandHandler("memory", memory_cmd))
    app.add_handler(CommandHandler("reset_private", reset_private_cmd))
    app.add_handler(CommandHandler("reset_group", reset_group_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app
