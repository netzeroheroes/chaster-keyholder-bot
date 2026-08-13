from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

from app.agent import ChatAgent
from app.bridge import GroupBridge
from app.chaster import ChasterClient
from app.chaster_actions import (
    ChasterIntent,
    extract_lock_commands,
    format_capabilities_reply,
    format_group_lock_confirm,
    format_truth_reply,
    parse_chaster_intent,
    run_chaster_intent,
    run_tour_step,
)
from app.chaster_tour import ChasterTour, wants_tour_next, wants_tour_start
from app.punish import (
    detect_rule_break,
    format_auto_punish_reply,
    is_direct_lock_order,
    is_mercy_plea,
)
from app.runtime_controls import get_controls
from app.scene_builder import build_scene_from_profile, wants_scene_build

# Read-only intents — Sub may ask; Domme may ask. No lock mutation.
_READ_ONLY_INTENTS = frozenset(
    {"list_kinks", "list_capabilities", "list_history", "list_extensions", "status"}
)
from app.images import ImageService
from app.memory import LongTermMemory
from app.persist import save_scene, save_sessions
from app.roles import (
    Room,
    Role,
    bot_label,
    format_user_line,
    session_id_for,
    speaker_label,
)
from app.scene import SceneState
from app.sessions import DisplayMessage, SessionStore

log = logging.getLogger(__name__)

# Phrases that mean the model is stuck asking Sub to choose
_LOOP_MARKERS = re.compile(
    r"(what do you think would be appropriate|"
    r"we'll have to think of a suitable punishment|"
    r"what (do you|would you) (think|suggest|want))",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _too_similar(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if len(na) > 40 and (na in nb or nb in na):
        return True
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    return len(ta & tb) / max(len(ta), len(tb)) >= 0.75


def _is_loop_text(text: str) -> bool:
    return bool(_LOOP_MARKERS.search(text or ""))


def _sanitize_history(
    history: list[ChatCompletionMessageParam],
) -> list[ChatCompletionMessageParam]:
    """Drop consecutive duplicate assistant turns that cause death-loops."""
    cleaned: list[ChatCompletionMessageParam] = []
    last_assistant = ""
    for msg in history:
        if msg.get("role") == "assistant":
            content = str(msg.get("content") or "")
            if last_assistant and _too_similar(content, last_assistant):
                continue
            last_assistant = content
        cleaned.append(msg)
    return cleaned


def _strip_looping_assistants(
    history: list[ChatCompletionMessageParam],
) -> list[ChatCompletionMessageParam]:
    """Remove assistant messages that match known loop patterns."""
    out: list[ChatCompletionMessageParam] = []
    for msg in history:
        if msg.get("role") == "assistant" and _is_loop_text(str(msg.get("content") or "")):
            continue
        out.append(msg)
    return out


def _recent_assistant_texts(history: list, limit: int = 4) -> list[str]:
    out: list[str] = []
    for msg in reversed(history):
        if msg.get("role") == "assistant" and msg.get("content"):
            out.append(str(msg["content"]))
            if len(out) >= limit:
                break
    return list(reversed(out))


def _domme_wants_decision(message: str) -> bool:
    return bool(
        re.search(
            r"(you (decide|choose|pick)|your choice|he (doesn'?t|does not) get|"
            r"no choice|decide for|punish(ment)? (him|now)|what (are we|should we) do)",
            message or "",
            re.IGNORECASE,
        )
    )


def _domme_hands_off(message: str) -> bool:
    """Mistress is busy / stepping away — AI should take the Sub solo."""
    return bool(
        re.search(
            r"\b("
            r"i('?m| am) busy|"
            r"busy for|"
            r"entertain (him|the\s+sub|boy)|"
            r"have fun with (him|the\s+sub|boy)|"
            r"keep him (busy|occupied|entertained)|"
            r"play with (him|the\s+sub|boy)|"
            r"take (over|care of him)|"
            r"you('?re| are) (in charge|on duty)|"
            r"leave (him|you) (with you|to you)|"
            r"brb|be right back|"
            r"stepping away|"
            r"back in \d+|"
            r"gone for|"
            r"occupy him|"
            r"watch him for me"
            r")\b",
            message or "",
            re.IGNORECASE,
        )
    )


def _hands_off_duration_hint(message: str) -> str:
    m = re.search(
        r"(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)\b",
        message or "",
        re.I,
    )
    if not m:
        return "a little while"
    n, unit = m.group(1), m.group(2).lower()
    if unit.startswith("h"):
        label = "hour" if float(n) == 1 else "hours"
    elif unit.startswith("m"):
        label = "minute" if float(n) == 1 else "minutes"
    else:
        label = "seconds"
    return f"about {n} {label}"


async def handle_chat_turn(
    *,
    agent: ChatAgent,
    store: SessionStore,
    scene: SceneState,
    memory: LongTermMemory,
    bridge: GroupBridge,
    images: ImageService | None = None,
    chaster: ChasterClient | None = None,
    role: Role,
    room: Room,
    message: str,
    chaster_role: str | None = None,
    chaster_username: str | None = None,
) -> dict[str, Any]:
    sid = session_id_for(room)
    raw_history = store.get(sid)
    history = _sanitize_history(raw_history)

    # If history is already poisoned with loop lines, cut them out before prompting
    if any(
        _is_loop_text(str(m.get("content") or ""))
        for m in history
        if m.get("role") == "assistant"
    ):
        history = _sanitize_history(_strip_looping_assistants(history))
        log.warning("Stripped looping assistant turns from %s history", room)

    handle = (chaster_username or "").strip().lstrip("@")
    if handle:
        # Keep memory names aligned with live Chaster handles when empty
        if role == "domme" and not (memory.domme_name or "").strip():
            memory.update_fields(domme_name=handle)
        if role == "sub" and not (memory.sub_name or "").strip():
            memory.update_fields(sub_name=handle)

    speaker = speaker_label(role, memory, chaster_username=handle or None)
    user_line = format_user_line(
        role,
        message,
        memory,
        chaster_role=chaster_role,
        chaster_username=handle or None,
        room=room,
    )
    hands_off = role == "domme" and _domme_hands_off(message)
    if role == "domme" and _domme_wants_decision(message) and not hands_off:
        if room == "group":
            user_line += (
                "\n\n[DIRECTOR: Domme delegated in GROUP. You MUST choose a concrete "
                "punishment NOW, announce it to BOY here, and start enforcing it. "
                "Do not ask BOY what he wants.]"
            )
        else:
            user_line += (
                "\n\n[DIRECTOR: Domme delegated in PRIVATE. Propose the concrete "
                "punishment to her here; use [[[GROUP]]] only if she wants him told now.]"
            )
    if hands_off:
        how_long = _hands_off_duration_hint(message)
        title = memory.domme_title or "Mistress"
        if room == "group":
            user_line += (
                f"\n\n[DIRECTOR: {title} is BUSY / handed the Sub to YOU for {how_long}. "
                "This is a TAKEOVER beat in GROUP (Sub can see this).\n"
                f"1) Briefly acknowledge {title} (one short line).\n"
                "2) Pivot hard to the Sub — open roughly like: "
                "\"Well… it's just the two of us. Let's have some fun.\" "
                f"(She'll be busy for {how_long}.)\n"
                "3) Give ONE concrete tease/order immediately (edges, posture, lock nudge). "
                "You may use [[[LOCK]]] tags.\n"
                "Do NOT ask what he wants. Do NOT wait for Mistress to come back. "
                "Do NOT claim YOU are busy/out — SHE is.]"
            )
        else:
            user_line += (
                f"\n\n[DIRECTOR: {title} is handing the Sub to you for {how_long}, but "
                "you are in PRIVATE chat. Confirm the plan with her here, then emit "
                "[[[GROUP]]] with the takeover line for the Sub (he only sees GROUP).]"
            )

    bot_name = bot_label(memory)

    # Domme scene builder: pick real toys from his profile and craft a scene
    if role == "domme" and wants_scene_build(message) and chaster and chaster.configured:
        try:
            st = await chaster.status()
            username = (
                (st.get("sub_username") or "").strip()
                or (memory.sub_name or "").strip()
            )
            if username:
                profile = await chaster.get_user_kink_profile(username)
                built = await build_scene_from_profile(
                    profile, message=message, room=room, web_enrich=True
                )
                user_line += built.brief
                log.info(
                    "Scene builder: toys=%s pattern=%s mood_check=%s",
                    built.toys,
                    built.pattern_id,
                    built.mood_check_first,
                )
            else:
                user_line += (
                    "\n\n[DIRECTOR: Scene build requested but no wearer username. "
                    "Ask Mistress which profile, or sync Chaster first.]"
                )
        except Exception:  # noqa: BLE001
            log.exception("Scene builder failed")
            user_line += (
                "\n\n[DIRECTOR: Could not load his toy profile. "
                "Still propose a chastity/denial scene without inventing a toy list.]"
            )

    # Domme Chaster orders — API is source of truth; action turns skip LLM claims
    chaster_note = ""
    chaster_truth_reply: str | None = None
    if chaster and chaster.configured:
        try:
            st = await chaster.status()
            updates: dict[str, str] = {}
            kh = (st.get("domme_username") or "").strip()
            wearer = (st.get("sub_username") or "").strip()
            if kh and not (memory.domme_name or "").strip():
                updates["domme_name"] = kh
            if wearer and not (memory.sub_name or "").strip():
                updates["sub_name"] = wearer
            if updates:
                memory.update_fields(**updates)
                log.info("Synced names from Chaster: %s", updates)
        except Exception:  # noqa: BLE001
            log.exception("Chaster name sync failed")

        context_bits: list[str] = []
        for msg in history[-10:]:
            content = str(msg.get("content") or "")
            if content:
                context_bits.append(content)
        context_bits.append(message)
        context = "\n".join(context_bits)

        tour = ChasterTour.load()
        intent = parse_chaster_intent(message, context=context)

        # Stepwise feature tour: "1 by 1" / "next"
        if role == "domme" and (
            wants_tour_start(message)
            or wants_tour_next(message)
            or (intent and intent.kind == "tour_step")
        ):
            if wants_tour_start(message) or not tour.active:
                tour.start()
            step = tour.peek()
            if step is None:
                chaster_truth_reply = (
                    "Mistress — that's the end of the list for now. "
                    "Want add/remove time, freeze, hide/show his timer, or pillory? "
                    "Just give the order."
                )
            else:
                step_num = tour.index + 1
                step_total = len(tour.steps)
                result = await run_tour_step(
                    chaster, step, requested_by=speaker
                )
                tour.advance()
                chaster_truth_reply = format_truth_reply(
                    requested_by=speaker,
                    step_label=str(step.get("label") or step.get("id")),
                    step_num=step_num,
                    step_total=step_total,
                    result=result,
                    more_remaining=tour.active,
                )
                chaster_note = f"\n\n[{result.facts}]"
                log.info(
                    "Chaster tour step %s/%s %s -> blocked=%s",
                    step_num,
                    step_total,
                    step.get("id"),
                    result.blocked,
                )
            intent = None  # already handled

        if intent and intent.kind != "tour_step":
            is_readonly = intent.kind in _READ_ONLY_INTENTS
            if role != "domme" and not is_readonly:
                # Sub may BEG for mercy; may not ORDER lock changes
                if is_mercy_plea(message):
                    chaster_note += (
                        "\n\n[DIRECTOR: Sub is BEGGING for lock mercy "
                        f"(wanted: {intent.kind}). He may beg YOU or Mistress — both of "
                        "you are Dominants. Do NOT scold him for addressing Mistress. "
                        "Either Dominant may grant or deny. If YOU grant, emit a [[[LOCK]]] "
                        "tag. If denying, tease — begging is allowed; orders are not.]"
                    )
                elif is_direct_lock_order(message):
                    chaster_note += (
                        "\n\n[DIRECTOR: Sub tried to ORDER a lock change "
                        f"({intent.kind}). Refuse. He may beg you or Mistress politely — "
                        "he may not give orders. Correct him sharply. Auto-punish may apply.]"
                    )
                else:
                    chaster_note += (
                        "\n\n[DIRECTOR: Sub mentioned a lock change. Mistress and YOU "
                        "both control Chaster — he does not. If it was a plea, tease or "
                        "decide; if an order, shut it down. No lock mutation from Sub "
                        "speech alone (use [[[LOCK]]] if YOU grant).]"
                    )
                intent = None
            elif role != "domme" and is_readonly:
                result = await run_chaster_intent(
                    chaster, intent, requested_by=speaker
                )
                if result.ok and intent.kind == "list_kinks":
                    # Sub asked about toys/kinks — feed facts to LLM for scene suggestions
                    chaster_note = (
                        f"\n\n[{result.facts}]\n"
                        "[DIRECTOR: Sub asked about toys/kinks. Using HIS real profile list above, "
                        "suggest 2-3 suitable toys/kinks for the current tease/denial scene. "
                        "Stay in character. Do not claim you changed his lock.]"
                    )
                    log.info("Injected kink profile for Sub question")
                elif result.ok and intent.kind == "status":
                    chaster_note = (
                        f"\n\n[{result.facts}]\n"
                        "[DIRECTOR: Sub asked about lock status. Tease with the real remaining/"
                        "frozen/timer-visibility facts. Do not invent numbers.]"
                    )
                elif result.ok and intent.kind == "list_capabilities":
                    chaster_truth_reply = (
                        "BOY — lock control is for Mistress and me. "
                        "You don't get the control menu. Ask about your cage, toys, or orders."
                    )
                else:
                    chaster_note = (
                        "\n\n[DIRECTOR: Could not load his profile/toys. "
                        "Stay in scene without inventing a catalog.]"
                    )
            else:
                result = await run_chaster_intent(
                    chaster,
                    intent,
                    requested_by=speaker,
                )
                if result.ok:
                    chaster_note = f"\n\n[{result.facts}]"
                    if intent.kind in (
                        "list_capabilities",
                        "list_kinks",
                        "list_history",
                        "list_extensions",
                    ):
                        chaster_truth_reply = format_capabilities_reply(result)
                    else:
                        chaster_truth_reply = format_truth_reply(
                            requested_by=speaker,
                            step_label=intent.kind,
                            step_num=1,
                            step_total=1,
                            result=result,
                            more_remaining=False,
                        )
                    log.info(
                        "Chaster intent %s ok blocked=%s",
                        intent.kind,
                        result.blocked,
                    )
                else:
                    chaster_truth_reply = (
                        "Mistress — that didn't take on his lock. "
                        "Nothing changed. Want me to try again?"
                    )
                    chaster_note = f"\n\n[CHASTER ERROR: {result.error}]"
                    log.warning("Chaster intent %s failed: %s", intent.kind, result.error)

        # Begging alone (even without parsed intent) — feed the scene, no punish
        if role == "sub" and not chaster_truth_reply and is_mercy_plea(message):
            if "[DIRECTOR: Sub is BEGGING" not in chaster_note:
                chaster_note += (
                    "\n\n[DIRECTOR: Sub is BEGGING (timer/time/unfreeze mercy) to the "
                    "Dommes. Allowed — he may beg Mistress or you. Refer to both of you "
                    "as Dominants. Either of you may grant/deny. If YOU grant, emit "
                    "[[[LOCK]]]. Never scold him for saying please Mistress.]"
                )

        # Automatic Chaster detriment first — lock is the bot's main lever
        # (skipped for begging; fires for direct orders / rule breaks)
        if role == "sub" and not chaster_truth_reply and not is_mercy_plea(message):
            try:
                ctrl = get_controls()
                punish_on = ctrl.auto_punish_enabled
                default_secs = ctrl.auto_punish_seconds
            except RuntimeError:
                punish_on = getattr(chaster.settings, "auto_punish_enabled", True)
                default_secs = getattr(chaster.settings, "auto_punish_seconds", 600)
            if punish_on and chaster.configured:
                br = detect_rule_break(message, role=role)
                if br:
                    # Prefer live Domme setting; fall back to pattern severity
                    punish_secs = int(default_secs or br.seconds or 600)
                    if br.seconds > punish_secs:
                        punish_secs = br.seconds
                    results = []
                    applied: list[str] = []
                    r1 = await run_chaster_intent(
                        chaster,
                        ChasterIntent(kind="add_time", seconds=max(60, punish_secs)),
                        requested_by=f"{bot_name} (auto-punish)",
                    )
                    results.append(r1)
                    if r1.ok and not r1.blocked:
                        applied.append("add_time")
                    if br.freeze:
                        rf = await run_chaster_intent(
                            chaster,
                            ChasterIntent(kind="freeze"),
                            requested_by=f"{bot_name} (auto-punish)",
                        )
                        results.append(rf)
                        if rf.ok and not rf.blocked:
                            applied.append("freeze")
                    if br.hide_timer:
                        rh = await run_chaster_intent(
                            chaster,
                            ChasterIntent(kind="hide_time"),
                            requested_by=f"{bot_name} (auto-punish)",
                        )
                        results.append(rh)
                        if rh.ok and not rh.blocked:
                            applied.append("hide_time")
                    truth = format_auto_punish_reply(
                        bot_name=bot_name,
                        reason=br.reason,
                        results=results,
                        seconds=punish_secs,
                        applied=applied,
                    )
                    if truth:
                        # Skip LLM — consequence hits immediately via Chaster
                        chaster_truth_reply = truth
                        log.info("Auto-punish applied for %s", br.reason)
                    else:
                        chaster_note += (
                            f"\n\n[AUTO-PUNISH attempted for: {br.reason} but lock "
                            "change failed. Punish in-scene without inventing lock numbers.]"
                        )

        user_line += chaster_note

    recent = _recent_assistant_texts(history)
    if room == "private":
        anti_loop = (
            "\n\nHARD RULES THIS TURN (PRIVATE CHANNEL):\n"
            f"- You are ONLY talking to {speaker} (human Domme). The Sub cannot see this.\n"
            f"- Your name is '{bot_name}'. You are the AI Domme/keyholder — not her stand-in body.\n"
            "- Plan, scheme, encourage her meanness. Do not perform for the Sub here.\n"
            "- To speak to the Sub, emit [[[GROUP]]]…[[[/GROUP]]] (that posts to Group).\n"
            "- Never claim lock changes unless confirmed by real lock facts this turn.\n"
            "- If YOU grant a lock change from private, emit [[[LOCK]]]…[[[/LOCK]]].\n"
            "- Never invent reminder schedules. Never repeat a previous bot message.\n"
            "- Do not pretend this reply is already in Group unless you emitted GROUP tags.\n"
        )
    else:
        anti_loop = (
            "\n\nHARD RULES THIS TURN (GROUP CHANNEL):\n"
            f"- The human speaking this turn is: {speaker}. Address them correctly.\n"
            f"- Your name in chat is '{bot_name}'. You are the AI Domme/keyholder — "
            "never claim to be the human Domme or Sub.\n"
            "- GROUP audience: Domme + Sub + you. Everyone sees your reply.\n"
            "- You and the human Domme are BOTH Dominants; either may decide lock actions.\n"
            "- When Domme gives a lock order, back her in-scene here (Sub hears it).\n"
            "- Sub may BEG either Dominant for mercy. Never scold him for addressing Mistress.\n"
            "- Sub may NOT give direct lock orders. Orders get refused (and may be punished).\n"
            "- Never ask the Sub what punishment they want when Dommes are deciding.\n"
            "- If YOU grant a lock change, emit [[[LOCK]]]…[[[/LOCK]]] so Chaster actually runs.\n"
            "- Never claim lock changes without LOCK tags or confirmed facts this turn.\n"
            "- Lock history messages (custom logs) are real and may push-notify him — use them.\n"
            "- Reminder schedules still cannot be set via API; don't invent those.\n"
            "- Never repeat a previous bot message.\n"
            "- Advance with a NEW concrete order or punishment.\n"
            "- Do not workshop private strategy out loud; execute.\n"
        )
    if recent:
        listed = "\n".join(f"- {t[:200]}" for t in recent)
        anti_loop += f"Banned recent bot lines (do not reuse):\n{listed}\n"

    system_prompt = (
        scene.system_prompt_for(room)
        + "\n\n"
        + memory.prompt_block(room=room)
        + anti_loop
    )

    store.append_display(
        DisplayMessage(speaker=speaker, content=message, room=room)
    )

    # Chaster action turns: API truth only (no LLM hallucination)
    if chaster_truth_reply:
        reply = chaster_truth_reply
        messages = list(history) + [
            {"role": "user", "content": user_line},
            {"role": "assistant", "content": reply},
        ]
    else:
        reply, messages = await agent.reply(
            user_line,
            history=history,
            system_prompt=system_prompt,
        )

    # Retry up to 2 times if still looping (skip for API-truth Chaster replies)
    if not chaster_truth_reply:
        for attempt in range(2):
            stuck = (recent and _too_similar(reply, recent[-1])) or _is_loop_text(reply)
            if not stuck:
                break
            log.warning(
                "Loop detected in %s (attempt %s) — forced rewrite", room, attempt + 1
            )
            clean_hist = _sanitize_history(_strip_looping_assistants(history))
            short: list[ChatCompletionMessageParam] = []
            for msg in clean_hist[-8:]:
                if msg.get("role") in ("user", "assistant"):
                    if msg.get("role") == "assistant" and _too_similar(
                        str(msg.get("content") or ""), reply
                    ):
                        continue
                    short.append(msg)

            rewrite_user = (
                f"{user_line}\n\n"
                "[SYSTEM: You are looping. Write a completely different reply. "
                "Acknowledge Mistress, announce ONE specific cruel punishment for BOY "
                "(e.g. locked longer, edges with no release, corner time, lines, ice, "
                "denied orgasm for X days), and give the first order to start it. "
                "Do not ask BOY what he wants.]"
            )
            reply, messages = await agent.reply(
                rewrite_user,
                history=short,
                system_prompt=system_prompt
                + "\nOUTPUT REQUIREMENT: new decisive punishment + first order. No questions to Sub about choosing.",
            )

        if _is_loop_text(reply) or (recent and _too_similar(reply, recent[-1])):
            log.error("Model still looping — using decisive fallback line")
            if hands_off:
                how_long = _hands_off_duration_hint(message)
                title = memory.domme_title or "Mistress"
                reply = (
                    f"{title} — I've got him.\n\n"
                    f"BOY… {title} is busy for {how_long}, so it's just the two of us. "
                    "Let's have some fun. Hands on your cage — slow strokes for sixty "
                    "seconds. No cumming. Start now."
                )
            else:
                reply = (
                    "Mistress, thank you — I'll take this. BOY, you came without permission, "
                    "so you don't get a vote. Punishment: you're locked, denied, and you will "
                    "edge twice tonight under our count with no orgasm — then cage back on. "
                    "Stroke slow for sixty seconds starting now. Mistress, want me to make the "
                    "edges nastier?"
                )
            messages = list(history) + [
                {"role": "user", "content": user_line},
                {"role": "assistant", "content": reply},
            ]

        # Hands-off must always produce a Sub-facing takeover (don't stay silent/vague)
        if hands_off and room == "group":
            low = (reply or "").lower()
            weak = (
                not reply
                or len(reply.strip()) < 40
                or (
                    "two of us" not in low
                    and "just us" not in low
                    and "just the two" not in low
                    and "in charge" not in low
                    and "entertain" not in low
                    and "have some fun" not in low
                    and "fun with" not in low
                )
            )
            if weak:
                how_long = _hands_off_duration_hint(message)
                title = memory.domme_title or "Mistress"
                reply = (
                    f"{title} — leave him with me.\n\n"
                    f"Well, BOY… it's just the two of us for {how_long}. "
                    "Let's have some fun. Cage in hand — slow strokes. "
                    "No release unless I say. Begin."
                )
                messages = list(history) + [
                    {"role": "user", "content": user_line},
                    {"role": "assistant", "content": reply},
                ]
                log.info("Forced hands-off takeover line in group")

    group_posts: list[str] = []
    image_urls: list[str] = []
    visible_reply = reply

    # AI Domme self-grants via [[[LOCK]]] tags (either Dominant may decide)
    if visible_reply and "[[[LOCK]]]" in visible_reply.upper():
        cleaned, lock_intents = extract_lock_commands(visible_reply)
        # Always strip tags from what the Sub/Domme see
        visible_reply = cleaned
        if chaster and chaster.configured and not chaster_truth_reply and lock_intents:
            confirms: list[str] = []
            title = memory.domme_title or "Mistress"
            for lint in lock_intents[:4]:
                result = await run_chaster_intent(
                    chaster, lint, requested_by=f"{bot_name} (AI Domme)"
                )
                conf = format_group_lock_confirm(
                    bot_name=bot_name,
                    domme_title=title,
                    intent=lint,
                    result=result,
                )
                if conf:
                    confirms.append(conf)
                elif not result.ok:
                    log.warning("AI LOCK tag failed %s: %s", lint.kind, result.error)
                    confirms.append(
                        f"(Lock action `{lint.kind}` failed — nothing changed.)"
                    )
            if confirms:
                visible_reply = (
                    (visible_reply + "\n\n" + "\n\n".join(confirms)).strip()
                    if visible_reply
                    else "\n\n".join(confirms)
                )
        elif lock_intents and not (chaster and chaster.configured):
            visible_reply = (
                (visible_reply + "\n\n(Chaster not linked — lock tags ignored.)").strip()
            )
        elif "[[[LOCK]]]" in (reply or "").upper() and not lock_intents:
            visible_reply = (
                visible_reply
                + "\n\n(I meant to change the lock but the command was malformed — try again.)"
            ).strip()
        if messages and messages[-1].get("role") == "assistant":
            messages[-1] = {"role": "assistant", "content": visible_reply}

    if room == "private" and role == "domme":
        visible_reply, group_posts = await bridge.maybe_initiate_from_private(
            agent=agent,
            scene=scene,
            store=store,
            domme_message=message,
            private_reply=reply,
            speaker=bot_name,
        )
        if messages and messages[-1].get("role") == "assistant":
            messages[-1] = {"role": "assistant", "content": visible_reply}

    # Optional [[[IMAGE]]] prompts from the model (or Domme asking for a tease pic)
    image_errors: list[str] = []
    if images and images.enabled:
        cleaned, img_prompts = images.extract_prompts(visible_reply)
        wants_pic = role == "domme" and bool(
            re.search(
                r"\b(send|generate|make|create)\b.*\b(pic|picture|image|photo)\b",
                message,
                re.I,
            )
        )
        if not img_prompts and wants_pic:
            # Turn Domme's order into a usable visual prompt
            img_prompts = [
                "Adult 18+ teasing photo for a chastity cuckhold scene: "
                "Mistress on a date with another man, intimate restaurant mood, "
                "hand-holding, Sub denied and locked at home — sensual, not extreme gore"
            ]
        if img_prompts:
            # Always strip tags once we intend to generate (even if cleaned is empty)
            visible_reply = cleaned
            target_room: Room = "group" if (room == "private" or wants_pic) else room
            for prompt in img_prompts[:2]:
                try:
                    result = await images.generate(prompt)
                    image_urls.append(result["url"])
                    store.append_display(
                        DisplayMessage(
                            speaker=bot_name,
                            content="Sent a tease picture.",
                            room=target_room,
                            image_url=result["url"],
                        )
                    )
                    if target_room == "group" and room == "private":
                        visible_reply = (
                            (visible_reply + "\n\n— Sent tease picture to group —").strip()
                            if visible_reply
                            else "— Sent tease picture to group —"
                        )
                except Exception as exc:  # noqa: BLE001
                    log.exception("Image generation failed for prompt")
                    image_errors.append(str(exc))

            if image_errors and not image_urls:
                err = image_errors[0]
                visible_reply = (
                    f"{visible_reply}\n\n(Image failed: {err})".strip()
                    if visible_reply
                    else f"(Image failed: {err})"
                )
    elif images is not None and not images.enabled and role == "domme" and re.search(
        r"\b(pic|picture|image|photo)\b", message, re.I
    ):
        visible_reply = (
            f"{visible_reply}\n\n(Image generation is disabled — set IMAGE_ENABLED=true)".strip()
            if visible_reply
            else "(Image generation is disabled — set IMAGE_ENABLED=true)"
        )

    # Persist sanitized history + new turn (don't keep feeding duplicates)
    store.set(sid, _sanitize_history(messages))
    if visible_reply:
        store.append_display(
            DisplayMessage(speaker=bot_name, content=visible_reply, room=room)
        )

    save_sessions(store)
    save_scene(scene)

    asyncio.create_task(
        _safe_consolidate(
            memory,
            agent,
            room=room,
            speaker=speaker,
            user_text=message,
            bot_text=visible_reply,
        )
    )

    return {
        "reply": visible_reply,
        "room": room,
        "role": role,
        "group_posts": group_posts,
        "image_urls": image_urls,
    }


async def _safe_consolidate(
    memory: LongTermMemory,
    agent: ChatAgent,
    *,
    room: str,
    speaker: str,
    user_text: str,
    bot_text: str,
) -> None:
    try:
        await memory.consolidate_from_turn(
            agent,
            room=room,
            speaker=speaker,
            user_text=user_text,
            bot_text=bot_text,
        )
    except Exception:
        log.exception("Background memory consolidate failed")
