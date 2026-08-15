from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from threading import Lock

from openai.types.chat import ChatCompletionMessageParam

from app.agent import ChatAgent
from app.roles import session_id_for
from app.scene import SceneState
from app.sessions import DisplayMessage, SessionStore

log = logging.getLogger(__name__)

GROUP_BLOCK = re.compile(
    r"\[\[\[GROUP\]\]\](.*?)\[\[\[/GROUP\]\]\]",
    re.DOTALL | re.IGNORECASE,
)

GROUP_INTENT = re.compile(
    r"("
    r"\bgroup\b|"
    r"tell (the )?(sub|him|boy)|"
    r"tease (the )?(sub|him|boy)|"
    r"say (to|in) (the )?group|"
    r"post (in|to)|"
    r"go (into|to) (the )?group|"
    r"speak (in|to) (the )?(group|sub)|"
    r"address the sub|"
    r"message the sub|"
    r"in (the )?group chat|"
    r"announce (to|in)|"
    r"\bexecute\b|"
    r"start the (scene|plan)|"
    r"begin the (scene|plan)|"
    r"carry (it|the plan) out|"
    r"run (the )?(scene|plan)|"
    r"make it happen|"
    r"do it (now|in (the )?group)|"
    r"i('m| am) going out|"
    r"going out tonight|"
    r"leave you in charge|"
    r"you('re| are) in charge|"
    r"i('m| am) busy|"
    r"entertain (him|the sub|boy)|"
    r"have fun with (him|the sub|boy)"
    r")",
    re.IGNORECASE,
)

DOMME_GOING_OUT = re.compile(
    r"\b("
    r"i('m| am) going out|"
    r"going out tonight|"
    r"i('m| am) (going )?on a date|"
    r"on a date|"
    r"date night"
    r")\b",
    re.IGNORECASE,
)

# AI wrongly claiming the Domme's night out as its own
STEALS_NIGHT_OUT = re.compile(
    r"("
    r"while i enjoy an evening out|"
    r"i('m| am) going out|"
    r"i enjoy an evening|"
    r"while i('m| am) out|"
    r"await my return|"
    r"i('ll| will) be (out|with a|with another)|"
    r"handsome gentleman tonight|"
    r"how he will take care of me"
    r")",
    re.IGNORECASE,
)

CORRECT_IN_CHARGE = re.compile(
    r"("
    r"mistress is going out|"
    r"she('s| is) going out|"
    r"i('m| am) in charge|"
    r"i am in charge|"
    r"left me in charge|"
    r"she('s| is) out"
    r")",
    re.IGNORECASE,
)

SendFn = Callable[[str], Awaitable[None]]


class GroupBridge:
    """Posts bot-initiated lines into the shared group (web + optional Telegram)."""

    def __init__(self) -> None:
        self._send: SendFn | None = None
        self._lock = Lock()

    def set_telegram_sender(self, send: SendFn | None) -> None:
        with self._lock:
            self._send = send

    def split_private_reply(self, text: str) -> tuple[str, list[str]]:
        posts = [m.strip() for m in GROUP_BLOCK.findall(text or "") if m.strip()]
        private = GROUP_BLOCK.sub("", text or "").strip()
        private = re.sub(r"\n{3,}", "\n\n", private).strip()
        return private, posts

    def wants_group_post(self, domme_message: str) -> bool:
        from app.speaker_guard import planning_stays_private, wants_him_told

        text = domme_message or ""
        if wants_him_told(text):
            return True
        if planning_stays_private(text):
            return False
        return bool(GROUP_INTENT.search(text))

    def inject_private_note(
        self,
        store: SessionStore,
        text: str,
        *,
        speaker: str = "Keyholder",
    ) -> None:
        """Keyholder-only note so a group beat can continue in private."""
        sid = session_id_for("private")
        history = store.get(sid)
        history.append({"role": "assistant", "content": text})
        store.set(sid, history)
        store.append_display(
            DisplayMessage(speaker=speaker or "Keyholder", content=text, room="private")
        )

    def inject_group_bot_message(
        self,
        store: SessionStore,
        text: str,
        *,
        speaker: str = "Keyholder",
    ) -> None:
        sid = session_id_for("group")
        history = store.get(sid)
        assistant: ChatCompletionMessageParam = {
            "role": "assistant",
            "content": text,
        }
        history.append(assistant)
        store.set(sid, history)
        store.append_display(
            DisplayMessage(speaker=speaker or "Keyholder", content=text, room="group")
        )

    async def publish_group_messages(
        self,
        store: SessionStore,
        posts: list[str],
        *,
        speaker: str = "Keyholder",
    ) -> list[str]:
        published: list[str] = []
        for post in posts:
            self.inject_group_bot_message(store, post, speaker=speaker)
            published.append(post)
            send = None
            with self._lock:
                send = self._send
            if send is not None:
                try:
                    await send(post)
                except Exception:
                    log.exception("Failed to send group message via Telegram")
        return published

    def _fallback_in_charge_line(self, domme_message: str) -> str:
        cuck = bool(re.search(r"cuck", domme_message or "", re.I))
        tease = (
            "While she's out getting what you can't give her, you stay caged — "
            "my little cuck for the night. Think about her enjoying herself. "
            "You don't get to cum. You wait for us."
            if cuck
            else "You stay caged under my watch. No release. Be useful and obedient until she's back."
        )
        return (
            "BOY — your Domme is going out tonight, so I'm in charge of you. "
            + tease
        )

    async def _fix_identity(
        self,
        *,
        agent: ChatAgent,
        scene: SceneState,
        domme_message: str,
        post: str,
    ) -> str:
        """If Domme is going out, ensure the AI doesn't steal her night."""
        if not DOMME_GOING_OUT.search(domme_message or ""):
            return post

        bad = STEALS_NIGHT_OUT.search(post or "") or not CORRECT_IN_CHARGE.search(
            post or ""
        )
        if not bad:
            return post

        log.warning("Group post stole Domme's night out — rewriting")
        rewrite_system = (
            "Rewrite the group message. Output ONLY the corrected message.\n"
            "You are the AI Domme (Dominant). The human Domme is going out — use her "
            "real name, never the characters {her name}.\n"
            "MUST include: she is going out tonight + you are in charge of the Sub.\n"
            "Tease him (cuck/denial if relevant). "
            "FORBIDDEN: saying YOU are going out, on the date, or with the gentleman.\n"
            "You are Dominant — never obedient/submissive."
        )
        rewrite_user = (
            f"Domme order: {domme_message}\n\n"
            f"Bad draft to fix:\n{post}\n\n"
            "Corrected group message:"
        )
        try:
            fixed, _ = await agent.reply(
                rewrite_user,
                history=[],
                system_prompt=rewrite_system,
            )
            fixed, _ = self.split_private_reply(fixed.strip())
            if (
                fixed
                and not STEALS_NIGHT_OUT.search(fixed)
                and CORRECT_IN_CHARGE.search(fixed)
            ):
                return fixed
        except Exception:
            log.exception("Identity rewrite failed")

        return self._fallback_in_charge_line(domme_message)

    async def maybe_initiate_from_private(
        self,
        *,
        agent: ChatAgent,
        scene: SceneState,
        store: SessionStore,
        domme_message: str,
        private_reply: str,
        speaker: str = "Keyholder",
        domme_name: str = "",
        sub_name: str = "",
    ) -> tuple[str, list[str]]:
        from app.speaker_guard import (
            brief_private_delivery,
            claims_group_delivery,
            fill_placeholders,
            planning_stays_private,
            private_should_be_brief,
            soften_group_tease,
            strip_invented_night_out,
            wants_him_told,
        )

        visible, posts = self.split_private_reply(private_reply)
        her = (domme_name or "").strip() or "the keyholder"
        if posts and planning_stays_private(domme_message) and not wants_him_told(
            domme_message
        ):
            log.warning("Dropped GROUP cross-post so the plan stays private")
            posts = []

        craft_system = (
            "You are the AI helper in a shared adult D/s group chat.\n"
            "You are Dominant and here to have fun. Never obedient or submissive.\n"
            f"The human keyholder's name is {her}. Use that name. Never write {{her name}}.\n"
            "You are NOT her.\n"
            "Output ONLY one short mystery tease — no quotes, no preamble, no list.\n"
            "Do not reveal her plan, toys she will use, a schedule, or what happens later.\n"
            "He should wonder, not know.\n"
            "Only mention her going out / a date if her order actually says that. "
            "Do not invent a night out.\n"
            "NEVER claim you are going out or on her date.\n"
            "Never involve anyone under 18."
        )

        if not posts and self.wants_group_post(domme_message):
            craft_user = (
                f"Human Domme's private order:\n{domme_message}\n\n"
                f"Your private note:\n{visible or private_reply}\n\n"
                "Write ONE short mystery tease for the lockee. Do not whisper. "
                "Do not reveal the plan."
            )
            try:
                crafted, _ = await agent.reply(
                    craft_user,
                    history=[],
                    system_prompt=craft_system,
                )
                crafted = crafted.strip()
                crafted, _ = self.split_private_reply(crafted)
                if crafted and crafted.upper() != "NO_GROUP_POST":
                    posts = [crafted]
            except Exception:
                log.exception("Failed to craft group initiation message")

        # Always run when Domme says she's going out, even if model emitted tags
        if not posts and DOMME_GOING_OUT.search(domme_message or ""):
            posts = [self._fallback_in_charge_line(domme_message)]
        if not posts and (
            wants_him_told(domme_message)
            or claims_group_delivery(visible)
            or claims_group_delivery(private_reply)
        ):
            posts = [soften_group_tease(
                "Something's coming. Stay with that ache — she hasn't promised you the details."
            )]

        fixed_posts: list[str] = []
        for post in posts:
            fixed = await self._fix_identity(
                agent=agent,
                scene=scene,
                domme_message=domme_message,
                post=post,
            )
            fixed = fill_placeholders(
                fixed, domme_name=domme_name, sub_name=sub_name
            )
            fixed = strip_invented_night_out(
                fixed, user_message=domme_message
            )
            if fixed.strip():
                fixed_posts.append(soften_group_tease(fixed))
        # Dedupe while preserving order
        posts = list(dict.fromkeys(fixed_posts))

        # Model sometimes fakes our delivery marker in the private reply — strip it
        visible = re.sub(
            r"—\s*Sent to group\s*—[\s\S]*$",
            "",
            visible or "",
            flags=re.IGNORECASE,
        ).strip()
        if DOMME_GOING_OUT.search(domme_message or "") and STEALS_NIGHT_OUT.search(
            visible or ""
        ):
            visible = ""
        if posts and wants_him_told(domme_message) and (
            private_should_be_brief(visible) or not visible
        ):
            visible = brief_private_delivery()

        if posts:
            await self.publish_group_messages(store, posts, speaker=speaker)
            note = "\n\n— Sent to group —\n" + "\n---\n".join(posts)
            visible = (visible + note).strip() if visible else note.strip()

        return visible, posts
