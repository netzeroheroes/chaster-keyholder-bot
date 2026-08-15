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
    fetch_live_status_block,
    format_capabilities_reply,
    format_group_lock_confirm,
    format_truth_reply,
    parse_chaster_intent,
    run_chaster_intent,
    run_tour_step,
)
from app.lock_guard import scrub_lock_hallucinations
from app.speaker_guard import (
    demands_beg_unlock,
    domme_teasing_lockee,
    fill_placeholders,
    fix_mixed_terms,
    has_chat_chrome,
    impersonates_human,
    looks_like_image_dump,
    mistreats_domme_as_sub,
    repair_bot_submissive,
    repair_confused_domme_reply,
    repair_domme_misaddress,
    repair_impersonation,
    repair_scripted_dialogue,
    rewrite_beg_unlock,
    rewrite_generic_mistress,
    collapse_idea_list,
    looks_like_plan_spoiler,
    planning_stays_private,
    soften_group_tease,
    sounds_like_bot_submissive,
    strip_chat_chrome,
    strip_impersonation,
    strip_invented_night_out,
    strip_leaked_instructions,
    strip_scripted_dialogue,
    strip_stage_directions,
    wants_to_be_free,
    writes_scripted_dialogue,
)
from app.cage_practice import PRACTICE_BLOCK, rewrite_caged_touch
from app.chaster_tour import ChasterTour, wants_tour_next, wants_tour_start
from app.extension_games import extension_punish_intents
from app.punish import (
    RuleBreak,
    bump_disobey_streak,
    cool_disobey_streak,
    detect_rule_break,
    escalate_rule_break,
    format_auto_punish_reply,
    is_direct_lock_order,
    is_mercy_plea,
    looks_like_obedience,
)
from app.runtime_controls import get_controls
from app.scene_builder import pick_toys, wants_scene_build
from app.scene_interview import (
    apply_interview_answer,
    format_guide_director,
    format_interview_director,
    start_interview,
    wants_cancel_interview,
)
from app.session_kit import (
    format_week_plan_private_note,
    format_week_planner_block,
    wants_week_plan,
)

# Read-only intents — Sub may ask; Domme may ask. No lock mutation.
_READ_ONLY_INTENTS = frozenset(
    {
        "list_kinks",
        "list_capabilities",
        "list_history",
        "list_extensions",
        "status",
    }
)
from app.images import (
    ImageService,
    prompt_from_request,
    strip_unsent_image_claims,
    user_facing_image_error,
)
from app.memory import LongTermMemory
from app.persist import save_scene, save_sessions
from app.roles import (
    Room,
    Role,
    bot_label,
    domme_address,
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


_THEY_SAID = re.compile(
    r"THEY SAID[^\n]*\n+\"\"\"\s*(.*?)\s*\"\"\"",
    re.S,
)
_LABEL_OPEN = re.compile(
    r"^\[(?:Domme|Sub|Keyholder)[^\]]*\]:\s*(.+)$",
    re.I,
)
_SPEAKER_OPEN = re.compile(
    r"^(?:Domme|Sub|Keyholder)(?:\s+\([^)]+\))?:\s*(.+)$",
    re.I,
)


def extract_spoken_user(content: str) -> str:
    """Pull the human's actual words out of a bloated prompt blob."""
    text = (content or "").strip()
    if not text:
        return ""
    m = _THEY_SAID.search(text)
    if m:
        return m.group(1).strip()
    first = text.splitlines()[0].strip()
    for pat in (_LABEL_OPEN, _SPEAKER_OPEN):
        hit = pat.match(first)
        if hit:
            return hit.group(1).strip()
    if first.startswith("[") and "]: " in first:
        return first.split("]: ", 1)[1].strip()
    # Old turns wrapped the line then dumped IDENTITY/ADDRESS
    if "\n[IDENTITY:" in text or "\n[ADDRESS:" in text:
        return first.split("]: ", 1)[-1].strip() if "]: " in first else first
    if "[DIRECTOR:" in text or "[CHASTER" in text:
        return first
    return text


def _clean_history_for_model(
    history: list[ChatCompletionMessageParam],
    *,
    limit: int = 24,
) -> list[ChatCompletionMessageParam]:
    """Keep a short real conversation — not last turn's rule dump."""
    cleaned: list[ChatCompletionMessageParam] = []
    for msg in history:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            spoken = extract_spoken_user(content)
            if not spoken:
                continue
            content = spoken
        cleaned.append({"role": role, "content": content})
    return cleaned[-limit:]


def _focus_user_payload(message: str, *, speaker: str, extras: str = "") -> str:
    said = (message or "").strip()
    parts = [
        "THEY SAID (answer this — do not ignore it):",
        f'"""{said}"""',
        f"Speaker: {speaker}. Reply to those words. Use the chat history as context.",
    ]
    extra = (extras or "").strip()
    if extra:
        parts.extend(["", "SIDE NOTES (not a replacement for THEY SAID):", extra[:1500]])
    parts.extend(
        [
            "",
            "Now answer THEY SAID. If they asked for a hint, drop one — not a list.",
        ]
    )
    return "\n".join(parts)


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
    history = _sanitize_history(_clean_history_for_model(raw_history))

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
    her = domme_address(memory)
    extra_notes: list[str] = [
        f"Speaker this turn: {speaker} "
        f"({'keyholder' if role == 'domme' else 'lockee'}).",
    ]
    user_line = ""  # filled after directors / chaster notes
    if role == "domme" and room == "group" and domme_teasing_lockee(message):
        extra_notes.append(
            "[DIRECTOR: Domme is teasing/naming the LOCKEE (e.g. hey slut). "
            "She is NOT insulting you. Join her — briefly ack, then order the lockee. "
            "NEVER write [You (@Keyholder): …]. NEVER address yourself as Keyholder. "
            "No fake UI labels.]"
        )
    hands_off = role == "domme" and _domme_hands_off(message)
    if role == "domme" and _domme_wants_decision(message) and not hands_off:
        if room == "group":
            extra_notes.append(
                "[DIRECTOR: Domme delegated in GROUP. You MUST choose a concrete "
                "punishment NOW, announce it to the lockee here, and start enforcing it. "
                "Do not ask him what he wants.]"
            )
        else:
            extra_notes.append(
                "[DIRECTOR: Domme delegated in PRIVATE. Propose the concrete "
                "punishment to her here; use [[[GROUP]]] only if she wants him told now.]"
            )
    if hands_off:
        how_long = _hands_off_duration_hint(message)
        title = her
        if room == "group":
            extra_notes.append(
                f"[DIRECTOR: {title} is BUSY / handed the Sub to YOU for {how_long}. "
                "This is a TAKEOVER beat in GROUP (Sub can see this). "
                f"Briefly ack {title}, then tease him. Do NOT claim YOU are out.]"
            )
        else:
            extra_notes.append(
                f"[DIRECTOR: {title} is handing the Sub to you for {how_long}, but "
                "you are in PRIVATE chat. Confirm the plan with her here, then emit "
                "[[[GROUP]]] with the takeover line for the Sub (he only sees GROUP).]"
            )

    bot_name = bot_label(memory)
    live_remaining = ""

    def _memory_command_result(reply: str) -> dict[str, Any]:
        sid_m = session_id_for(room)
        hist = list(store.get(sid_m))
        hist.append({"role": "user", "content": format_user_line(
            role, message, memory,
            chaster_role=chaster_role,
            chaster_username=handle or None,
            room=room,
        )})
        hist.append({"role": "assistant", "content": reply})
        store.set(sid_m, hist)
        store.append_display(DisplayMessage(speaker=speaker, content=message, room=room))
        store.append_display(DisplayMessage(speaker=bot_name, content=reply, room=room))
        save_sessions(store)
        return {
            "reply": reply,
            "room": room,
            "role": role,
            "group_posts": [],
            "image_urls": [],
        }

    # Explicit memory commands (Domme) — deterministic, not LLM
    if role == "domme":
        remember_fact = memory.parse_remember_command(message)
        forget_q = memory.parse_forget_command(message)
        if remember_fact:
            entry = memory.remember_fact(remember_fact, source=speaker)
            return _memory_command_result(
                f"Got it — locked into memory:\n• {entry}\n\n"
                "Ask me later with “what do you remember?” and I’ll recall it."
            )
        if forget_q:
            removed = memory.forget_fact(forget_q)
            if removed:
                listing = "\n".join(f"• {r}" for r in removed[:8])
                reply_m = f"Forgotten ({len(removed)}):\n{listing}"
            else:
                reply_m = f"Nothing matched “{forget_q}” in durable facts."
            return _memory_command_result(reply_m)
        if memory.wants_recall(message):
            return _memory_command_result(memory.format_recall_reply(for_domme=True))

    # Domme scene interview → keyholder guide (never invent live fiction)
    if role == "domme":
        iv = dict(scene.snapshot().get("scene_interview") or {})
        if wants_cancel_interview(message) and iv.get("active"):
            scene.update(scene_interview={"active": False, "step": "mode"})
            extra_notes.append(
                "[DIRECTOR: She cancelled the scene interview. "
                "Acknowledge briefly. Do not write a scene or invent events.]"
            )
        elif wants_scene_build(message) or iv.get("active"):
            if wants_scene_build(message) and not iv.get("active"):
                iv = start_interview()
            iv = apply_interview_answer(iv, message)
            updates: dict[str, Any] = {"scene_interview": iv}
            if iv.get("step") == "guide" and iv.get("mode"):
                updates["session_mode"] = iv["mode"]
            scene.update(**updates)
            if iv.get("step") == "guide":
                toys = list(scene.session_toys or [])
                hooks = list(scene.session_kinks or [])
                if chaster and chaster.configured:
                    try:
                        st = await chaster.status()
                        username = (
                            (st.get("sub_username") or "").strip()
                            or (memory.sub_name or "").strip()
                        )
                        if username:
                            profile = await chaster.get_user_kink_profile(username)
                            toys, hooks, _, _ = pick_toys(
                                profile,
                                count=max(2, min(4, len(toys) or 3)),
                                prefer_toys=toys,
                                prefer_kinks=hooks,
                            )
                    except Exception:  # noqa: BLE001
                        log.exception("Scene guide catalog failed")
                extra_notes.append(
                    format_guide_director(
                        iv, toys=toys, kinks=hooks, room=room
                    )
                )
                log.info(
                    "Scene guide ready mode=%s duration=%s toys=%s",
                    iv.get("mode"),
                    iv.get("duration"),
                    toys,
                )
            else:
                extra_notes.append(format_interview_director(iv, room=room))

    # Keyholder week plan — skeleton stays private even if she asked in Group
    if role == "domme" and wants_week_plan(message):
        if room == "private":
            extra_notes.append(
                format_week_planner_block(
                    kinks=list(scene.session_kinks or []),
                    toys=list(scene.session_toys or []),
                    room=room,
                )
            )
        else:
            extra_notes.append(
                "[DIRECTOR: She asked to plan in GROUP. He can see this. "
                "One mystery tease — no week list, no toys, no what she will do.]"
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
            # Drop stale generic Mistress title once we know her real name
            if (updates.get("domme_name") or memory.domme_name) and (
                (memory.domme_title or "").strip().lower() in {"mistress", "miss"}
            ):
                updates["domme_title"] = ""
            if updates:
                memory.update_fields(**updates)
                log.info("Synced names from Chaster: %s", updates)

            # Pull Domme + Sub sex/sexuality/pronouns from public profiles
            people = [
                (
                    (memory.domme_name or kh or "").strip(),
                    "domme_gender",
                    "domme_sexuality",
                    "domme_pronouns",
                ),
                (
                    (memory.sub_name or wearer or "").strip(),
                    "sub_gender",
                    "sub_sexuality",
                    "sub_pronouns",
                ),
            ]
            demo_updates: dict[str, str] = {}
            for uname, gkey, skey, pkey in people:
                if not uname:
                    continue
                need = not (
                    (getattr(memory, gkey, "") or "").strip()
                    and (getattr(memory, skey, "") or "").strip()
                )
                if not need:
                    continue
                try:
                    overview = await chaster.get_user_profile_overview(uname)
                except Exception:  # noqa: BLE001
                    log.exception("Profile overview failed for %s", uname)
                    continue
                if not overview:
                    continue
                g = str(overview.get("gender") or "").strip()
                s = str(overview.get("sexual_orientation") or "").strip()
                p = str(overview.get("pronouns") or "").strip()
                if g and not (getattr(memory, gkey, "") or "").strip():
                    demo_updates[gkey] = g
                if s and s.lower() != "unspecified" and not (
                    getattr(memory, skey, "") or ""
                ).strip():
                    demo_updates[skey] = s
                if p and not (getattr(memory, pkey, "") or "").strip():
                    demo_updates[pkey] = p
            if demo_updates:
                memory.update_fields(**demo_updates)
                log.info("Synced profile demographics: %s", demo_updates)
        except Exception:  # noqa: BLE001
            log.exception("Chaster name sync failed")

        # Always inject a fresh lock snapshot so the model cannot invent numbers
        try:
            live = await fetch_live_status_block(chaster, requested_by=speaker)
            chaster_note = f"\n\n[{live}]"
            m_rem = re.search(
                r"- Remaining:\s*([^\n(]+)", live
            )
            if m_rem:
                live_remaining = m_rem.group(1).strip()
        except Exception:  # noqa: BLE001
            log.exception("Live Chaster status fetch failed")
            chaster_note = (
                "\n\n[CHASTER LIVE STATUS unavailable this turn. "
                "Do NOT invent remaining time, totals, or lock lengths.]"
            )

        try:
            from app.rad_lockbox import get_rad_client, summarize_lockbox

            rad = get_rad_client()
            if rad and rad.configured:
                box = summarize_lockbox(await rad.status_snapshot())
                label = box.get("label") or "unknown"
                state = box.get("lock_state") or ""
                extra = f" ({state})" if state and state not in {"unknown", ""} else ""
                chaster_note += f"\n\n[LOCKBOX: {label}{extra}]"
            else:
                chaster_note += "\n\n[LOCKBOX: not configured]"
        except Exception:  # noqa: BLE001
            log.exception("Lockbox status for model failed")
            chaster_note += "\n\n[LOCKBOX: status unavailable]"

        try:
            from app.hygiene_request import format_hygiene_director

            chaster_note += f"\n\n{format_hygiene_director()}"
        except Exception:  # noqa: BLE001
            log.exception("Hygiene director failed")

        context_bits: list[str] = []
        for msg in history[-10:]:
            content = str(msg.get("content") or "")
            if content:
                context_bits.append(content)
        context_bits.append(message)
        context = "\n".join(context_bits)

        # Pending hygiene: "15mins" / "no" is the unlock window — never a lock-time change
        if role == "domme":
            try:
                from app.hygiene_request import (
                    approve_hygiene,
                    deny_hygiene,
                    parse_kh_hygiene_reply,
                    snapshot as hygiene_live,
                )

                hyg = hygiene_live()
                if hyg.get("status") == "requested":
                    decision = parse_kh_hygiene_reply(
                        message,
                        default_seconds=int(hyg.get("allowed_seconds") or 600),
                    )
                    if decision:
                        kind, secs = decision
                        if kind == "deny":
                            deny_hygiene()
                            chaster_truth_reply = "Denied. He may request again."
                            if room == "group":
                                bridge.inject_private_note(
                                    store,
                                    "You denied hygiene. He may request again.",
                                    speaker=bot_name,
                                )
                        else:
                            view = approve_hygiene(allowed_seconds=secs)
                            mins = max(
                                1, int(view.get("allowed_seconds") or secs) // 60
                            )
                            chaster_truth_reply = (
                                f"{mins} minutes. I'll tell him Unlock is next to Group — "
                                "not the bargaining."
                            )
                            if room == "private":
                                store.append_display(
                                    DisplayMessage(
                                        speaker=bot_name,
                                        content=(
                                            "Unlock is next to Group. "
                                            "Lock before time's up or there will be a consequence."
                                        ),
                                        room="group",
                                    )
                                )
                            else:
                                bridge.inject_private_note(
                                    store,
                                    f"You approved {mins} min. He only sees Unlock.",
                                    speaker=bot_name,
                                )
                                chaster_truth_reply = (
                                    "Unlock is next to Group. "
                                    "Lock before time's up or there will be a consequence."
                                )
                        log.info("Hygiene %s via chat (%ss)", kind, secs)
            except Exception:  # noqa: BLE001
                log.exception("Hygiene chat approve failed")

        tour = ChasterTour.load()
        intent = None if chaster_truth_reply else parse_chaster_intent(
            message, context=context
        )

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
                    f"{her} — that's the end of the list for now. "
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
                        f"(wanted: {intent.kind}). He may beg YOU or {her} — both of "
                        f"you are Dominants. Do NOT scold him for addressing {her}. "
                        "Either Dominant may grant or deny. If YOU grant, emit a [[[LOCK]]] "
                        "tag. If denying, tease — begging is allowed; orders are not.]"
                    )
                elif is_direct_lock_order(message):
                    chaster_note += (
                        "\n\n[DIRECTOR: Sub tried to ORDER a lock change "
                        f"({intent.kind}). Refuse. He may beg you or {her} politely — "
                        "he may not give orders. Correct him sharply. Auto-punish may apply.]"
                    )
                else:
                    chaster_note += (
                        f"\n\n[DIRECTOR: Sub mentioned a lock change. {her} and YOU "
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
                        f"Lockee — lock control is for {her} and me. "
                        "You don't get the control menu. Ask about your cage, toys, or orders."
                    )
                elif result.ok and intent.kind in ("list_extensions", "list_history"):
                    # Honest API facts only — no LLM inventing jigsaw controls
                    chaster_truth_reply = format_capabilities_reply(result)
                else:
                    chaster_note = (
                        "\n\n[DIRECTOR: Could not load that read-only lock info. "
                        "Stay in scene without inventing extensions or catalogs.]"
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
                    if not result.blocked and intent.kind not in _READ_ONLY_INTENTS:
                        rem = ""
                        if isinstance(result.lock, dict):
                            rem = str(result.lock.get("remaining") or "")
                            live_remaining = rem or live_remaining
                        memory.log_lock_event(
                            action=intent.kind,
                            remaining=rem,
                            by=speaker,
                            detail=intent.reason or "",
                        )
                    log.info(
                        "Chaster intent %s ok blocked=%s",
                        intent.kind,
                        result.blocked,
                    )
                else:
                    chaster_truth_reply = (
                        f"{her} — that didn't take on his lock. "
                        "Nothing changed. Want me to try again?"
                    )
                    chaster_note = f"\n\n[CHASTER ERROR: {result.error}]"
                    log.warning("Chaster intent %s failed: %s", intent.kind, result.error)

        # Begging alone (even without parsed intent) — feed the scene, no punish
        if role == "sub" and not chaster_truth_reply and is_mercy_plea(message):
            cooled = cool_disobey_streak(memory, reset=False)
            if "[DIRECTOR: Sub is BEGGING" not in chaster_note:
                chaster_note += (
                    "\n\n[DIRECTOR: Sub is BEGGING (ease punishments / timer mercy) to the "
                    f"Dommes. Allowed — he may beg {her} or you. Refer to both of you "
                    "as Dominants. Either of you may grant/deny. If YOU grant, emit "
                    f"[[[LOCK]]]. Never scold him for addressing {her}. "
                    f"Disobedience streak cooled to {cooled}. "
                    "Do NOT tell him to beg for unlock.]"
                )
        elif role == "sub" and not chaster_truth_reply and looks_like_obedience(message):
            cooled = cool_disobey_streak(memory, reset=True)
            chaster_note += (
                f"\n\n[DIRECTOR: Lockee showed apology/obedience — disobedience streak "
                f"cleared (was cooling to {cooled}). Acknowledge briefly; do not pile on.]"
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
                    try:
                        ctrl = get_controls()
                        min_add = int(ctrl.min_add_time_seconds or 60)
                        max_add = int(ctrl.max_add_time_seconds or 86400)
                    except RuntimeError:
                        min_add = 60
                        max_add = int(
                            getattr(chaster.settings, "max_add_time_seconds", 0) or 86400
                        )
                    strike = bump_disobey_streak(memory)
                    # Floor at Domme auto_punish / min session; cap at max session add
                    base = max(int(default_secs or br.seconds or 600), br.seconds, min_add)
                    br = escalate_rule_break(
                        RuleBreak(
                            reason=br.reason,
                            seconds=base,
                            freeze=br.freeze,
                            hide_timer=br.hide_timer,
                            use_extensions=br.use_extensions,
                        ),
                        strike,
                        min_seconds=min_add,
                        max_seconds=max_add,
                    )
                    punish_secs = max(min_add, min(max_add, int(br.seconds)))
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
                    # Extension punishments (share links, tasks, pillory, verification)
                    if br.use_extensions:
                        share_add = share_remove = share_visits = 0
                        try:
                            for ext in await chaster.list_lock_extensions():
                                if str(ext.get("slug") or "") != "link":
                                    continue
                                cfg = ext.get("config") or {}
                                share_add = int(cfg.get("timeToAdd") or 0)
                                share_remove = int(cfg.get("timeToRemove") or 0)
                                share_visits = int(cfg.get("nbVisits") or 0)
                                break
                        except Exception:  # noqa: BLE001
                            log.debug(
                                "Could not read share-link config for punish",
                                exc_info=True,
                            )
                        for lint in extension_punish_intents(
                            strike,
                            reason=br.reason,
                            share_add=share_add,
                            share_remove=share_remove,
                            share_visits=share_visits,
                        )[:5]:
                            try:
                                rx = await run_chaster_intent(
                                    chaster,
                                    lint,
                                    requested_by=f"{bot_name} (auto-punish)",
                                )
                            except Exception:  # noqa: BLE001
                                log.exception("Extension punish %s failed", lint.kind)
                                continue
                            results.append(rx)
                            if rx.ok and not rx.blocked:
                                applied.append(lint.kind)
                    truth = format_auto_punish_reply(
                        bot_name=bot_name,
                        reason=br.reason,
                        results=results,
                        seconds=punish_secs,
                        applied=applied,
                        strike=strike,
                    )
                    if truth:
                        # Skip LLM — consequence hits immediately via Chaster
                        chaster_truth_reply = truth
                        rem = ""
                        for r in results:
                            if r.ok and isinstance(r.lock, dict) and r.lock.get("remaining"):
                                rem = str(r.lock.get("remaining"))
                        memory.log_lock_event(
                            action="auto_punish:" + (",".join(applied) or br.reason),
                            remaining=rem,
                            by=f"{bot_name} (auto-punish)",
                            detail=f"strike {strike}: {br.reason}",
                        )
                        log.info(
                            "Auto-punish strike=%s secs=%s for %s",
                            strike,
                            punish_secs,
                            br.reason,
                        )
                    else:
                        chaster_note += (
                            f"\n\n[AUTO-PUNISH attempted for: {br.reason} but lock "
                            "change failed. Punish in-scene without inventing lock numbers.]"
                        )

        extra_notes.append(chaster_note)

    if role == "sub" and room == "group" and wants_to_be_free(message):
        extra_notes.append(
            "[DIRECTOR: He wants to be free. Do NOT dump lock numbers or remaining time. "
            "Stay in the tease: maybe if he earns it. Continue a short journey beat. "
            f"Say you will discuss it with {her}. Never unlock. Never list Chaster facts.]"
        )

    recent = _recent_assistant_texts(history)
    title = domme_address(memory)
    sub_nm = (memory.sub_name or "").strip() or "the Sub"
    if room == "private":
        anti_loop = (
            "\nTHIS TURN — PRIVATE:\n"
            f"Talk to {title} only. Answer what she just said.\n"
            "Plans and hint lists stay here. [[[GROUP]]] only if she said "
            "tell him / drop him a hint — and that line must not reveal the plan.\n"
            "You cannot touch him. Tease, advise her, or change the lock.\n"
        )
    else:
        who = (
            f"She ({title}) just spoke — rephrase her beat as a short tease. Do not spoil the plan."
            if role == "domme"
            else f"He ({speaker}) just spoke — answer him. {title} is the keyholder."
        )
        anti_loop = (
            "\nTHIS TURN — GROUP:\n"
            f"{who}\n"
            f"You are {bot_name}. Short. No labels. No lock-number lectures.\n"
            "Physical play is hers. You tease, talk to her in private, or change the lock.\n"
            "Hygiene is buttons. Cage: no stroke/touch-yourself orders.\n"
        )
    if recent:
        listed = "\n".join(f"- {t[:80]}" for t in recent[-2:])
        anti_loop += f"Don't repeat:\n{listed}\n"

    system_prompt = (
        "READ THE HUMAN. The latest spoken words are in THEY SAID. "
        "Your reply must be about those words and the chat history. "
        "Do not ignore them for a generic tease or a numbered list.\n\n"
        + scene.system_prompt_for(room)
        + "\n\n"
        + memory.prompt_block(room=room)
        + anti_loop
        + "\n"
        + PRACTICE_BLOCK
    )

    user_line = _focus_user_payload(
        message,
        speaker=speaker,
        extras="\n\n".join(n for n in extra_notes if n and str(n).strip()),
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
                f"Acknowledge {title}, announce ONE specific punishment for the lockee "
                "(e.g. locked longer, edges with no release, corner time, lines), "
                "and give the first order to start it. Do not ask him what he wants.]"
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
                reply = (
                    f"{title} — I've got him.\n\n"
                    f"Lockee… {title} left you with me for {how_long}. "
                    "Hands on the cage — not through it. Feel how little "
                    "you can do. Stay denied. Start now."
                )
            else:
                reply = (
                    f"{title}, I've got this. Lockee, you came without permission, "
                    "so you don't get a vote. You're locked and denied — edge twice "
                    "tonight under our count, no orgasm, cage back on. "
                    f"Cage stays on. Sit with that ache. {title}, want it meaner?"
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
                title = domme_address(memory)
                reply = (
                    f"{title} — leave him with me.\n\n"
                    f"Lockee — {title} left you with me for {how_long}. "
                    "Hands on the cage. No stroking — you can't. Stay denied. Begin."
                )
                messages = list(history) + [
                    {"role": "user", "content": user_line},
                    {"role": "assistant", "content": reply},
                ]
                log.info("Forced hands-off takeover line in group")

        # Strict: kill invented lock numbers when no API action confirmed this turn
        had_action = (
            "CHASTER ACTION DONE" in chaster_note
            or "CHASTER ACTION BLOCKED" in chaster_note
        )
        scrubbed = scrub_lock_hallucinations(
            reply,
            live_remaining=live_remaining,
            had_action_facts=had_action,
        )
        if scrubbed:
            log.warning("Scrubbed lock hallucination in %s reply", room)
            reply = scrubbed
            messages = list(history) + [
                {"role": "user", "content": user_line},
                {"role": "assistant", "content": reply},
            ]

        # Strict: Domme must never be addressed as the locked Sub
        if role == "domme" and mistreats_domme_as_sub(
            reply, user_message=message
        ):
            log.warning("Repaired Domme-as-Sub misaddress in %s", room)
            reply = repair_domme_misaddress(
                domme_title=domme_address(memory),
                sub_name=memory.sub_name or "him",
                original_topic=message[:120],
            )
            messages = list(history) + [
                {"role": "user", "content": user_line},
                {"role": "assistant", "content": reply},
            ]

        # Strict: AI Domme must never sound obedient/submissive herself
        if sounds_like_bot_submissive(reply):
            log.warning("Repaired bot-as-submissive voice in %s", room)
            reply = repair_bot_submissive(
                bot_name=bot_name,
                domme_title=domme_address(memory),
                sub_name=memory.sub_name or "BOY",
            )
            messages = list(history) + [
                {"role": "user", "content": user_line},
                {"role": "assistant", "content": reply},
            ]

        # Prefer role words over Mistress; strip fake UI chrome / usernames in group
        if room == "group":
            cleaned = strip_chat_chrome(
                reply,
                sub_name=memory.sub_name or handle or "",
                domme_name=memory.domme_name or "",
                bot_name=bot_name,
            )
            if demands_beg_unlock(cleaned):
                cleaned = rewrite_beg_unlock(cleaned)
            # Meta self-talk / empty after chrome strip → repair
            broken = (
                not cleaned
                or len(cleaned) < 12
                or re.search(
                    r"\bYou\s*\(@?Keyholder\)|\[\s*You\b|Let's play with his cock,\s*Keyholder",
                    cleaned,
                    re.I,
                )
            )
            if broken and role == "domme":
                log.warning("Repaired confused Domme-turn reply in group")
                cleaned = repair_confused_domme_reply(message=message)
            if cleaned != reply:
                log.info("Stripped chat chrome / beg-unlock from group reply")
                reply = cleaned
                messages = list(history) + [
                    {"role": "user", "content": user_line},
                    {"role": "assistant", "content": reply},
                ]
        else:
            rewritten = rewrite_generic_mistress(reply, memory.domme_name or "")
            if rewritten != reply:
                reply = rewritten
                messages = list(history) + [
                    {"role": "user", "content": user_line},
                    {"role": "assistant", "content": reply},
                ]

        # Strict: never write fake BOY:/Keyholder: scripts or invent his actions
        if writes_scripted_dialogue(reply):
            log.warning("Stripped scripted dialogue from %s reply", room)
            cleaned = strip_scripted_dialogue(reply)
            if not cleaned or len(cleaned) < 20:
                cleaned = repair_scripted_dialogue(room=room)
            reply = cleaned
            messages = list(history) + [
                {"role": "user", "content": user_line},
                {"role": "assistant", "content": reply},
            ]

        # Strict: never let the model forge Domme/Sub speaker lines
        if impersonates_human(reply) or has_chat_chrome(reply):
            log.warning("Stripped human impersonation from %s reply", room)
            cleaned = strip_impersonation(reply)
            cleaned = strip_chat_chrome(
                cleaned,
                sub_name=memory.sub_name or handle or "",
                domme_name=memory.domme_name or "",
                bot_name=bot_name,
            )
            if not cleaned or len(cleaned) < 20:
                if role == "domme":
                    cleaned = repair_confused_domme_reply(message=message)
                else:
                    cleaned = repair_impersonation(
                        bot_name=bot_name,
                        domme_title="keyholder",
                        sub_name="lockee",
                    )
            reply = cleaned
            messages = list(history) + [
                {"role": "user", "content": user_line},
                {"role": "assistant", "content": reply},
            ]

    group_posts: list[str] = []
    image_urls: list[str] = []
    visible_reply = fill_placeholders(
        reply,
        domme_name=memory.domme_name or "",
        sub_name=memory.sub_name or "",
    )
    visible_reply = fix_mixed_terms(
        visible_reply,
        domme_name=memory.domme_name or "",
        sub_name=memory.sub_name or "",
    )
    visible_reply = strip_stage_directions(visible_reply)
    visible_reply = strip_leaked_instructions(visible_reply)
    if room == "group":
        raw_group = visible_reply
        softened = soften_group_tease(visible_reply)
        if softened != visible_reply:
            log.warning("Softened group tease (no spoilers / homework)")
            visible_reply = softened
        if (
            role == "domme"
            and planning_stays_private(message)
            and raw_group
            and looks_like_plan_spoiler(raw_group)
        ):
            try:
                bridge.inject_private_note(
                    store,
                    "He can see Group, so I kept the plan here:\n\n" + raw_group,
                    speaker=bot_name,
                )
            except Exception:  # noqa: BLE001
                log.exception("Could not move spoiled plan into private")
        if role == "domme" and wants_week_plan(message):
            try:
                bridge.inject_private_note(
                    store,
                    format_week_plan_private_note(
                        kinks=list(scene.session_kinks or []),
                        toys=list(scene.session_toys or []),
                    ),
                    speaker=bot_name,
                )
            except Exception:  # noqa: BLE001
                log.exception("Could not ping private with week plan")
    else:
        private_part, tagged_posts = bridge.split_private_reply(visible_reply)
        collapsed = collapse_idea_list(private_part)
        if collapsed != private_part:
            log.warning("Collapsed idea list in private")
        if tagged_posts:
            visible_reply = (
                collapsed
                + "\n\n"
                + "".join(
                    f"[[[GROUP]]]{soften_group_tease(p)}[[[/GROUP]]]\n"
                    for p in tagged_posts
                )
            ).strip()
        else:
            visible_reply = collapsed
    caged = rewrite_caged_touch(visible_reply)
    if caged != visible_reply:
        log.warning("Rewrote caged-touch order in %s reply", room)
        visible_reply = caged
    visible_reply = strip_chat_chrome(
        visible_reply,
        sub_name=memory.sub_name or "",
        domme_name=memory.domme_name or "",
        bot_name=bot_name,
    )
    night_clean = strip_invented_night_out(
        visible_reply, user_message=message
    )
    if night_clean != visible_reply:
        log.warning("Stripped invented night-out from %s reply", room)
        visible_reply = night_clean or visible_reply
    reply = visible_reply

    # AI Domme self-grants via [[[LOCK]]] tags (either Dominant may decide)
    if visible_reply and "[[[LOCK]]]" in visible_reply.upper():
        cleaned, lock_intents = extract_lock_commands(visible_reply)
        # Always strip tags from what the Sub/Domme see
        visible_reply = cleaned
        # Never let the model reward insolence with mercy actions
        if role == "sub" and lock_intents and detect_rule_break(message, role=role):
            mercy = {"remove_time", "unfreeze", "show_time"}
            locked_out = [i for i in lock_intents if i.kind in mercy]
            lock_intents = [i for i in lock_intents if i.kind not in mercy]
            if locked_out:
                log.warning(
                    "Blocked mercy LOCK tags after Sub rule-break: %s",
                    [i.kind for i in locked_out],
                )
                if not any(i.kind == "add_time" for i in lock_intents):
                    lock_intents.insert(
                        0,
                        ChasterIntent(kind="add_time", seconds=1800, reason="insolence"),
                    )
        if chaster and chaster.configured and not chaster_truth_reply and lock_intents:
            confirms: list[str] = []
            title = domme_address(memory)
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
                if result.ok and not result.blocked:
                    rem = ""
                    if isinstance(result.lock, dict):
                        rem = str(result.lock.get("remaining") or "")
                    memory.log_lock_event(
                        action=lint.kind,
                        remaining=rem,
                        by=f"{bot_name} (AI Domme)",
                        detail=lint.reason or "",
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
            domme_name=memory.domme_name or "",
            sub_name=memory.sub_name or "",
        )
        if messages and messages[-1].get("role") == "assistant":
            messages[-1] = {"role": "assistant", "content": visible_reply}

    # Image generation is parked (filters). Still strip leftover [[[IMAGE]]] tags.
    image_errors: list[str] = []
    if images:
        cleaned, _img_tags = images.extract_prompts(visible_reply)
        if _img_tags:
            visible_reply = cleaned
    if images and images.enabled:
        cleaned, img_prompts = images.extract_prompts(visible_reply)
        wants_pic = role == "domme" and bool(
            re.search(
                r"\b(send|generate|make|create|draw|post)\b.*\b(pic|picture|image|photo)\b",
                message,
                re.I,
            )
        )
        dumped = looks_like_image_dump(cleaned or visible_reply)
        if not img_prompts and (wants_pic or dumped):
            img_prompts = [prompt_from_request(message)]
        elif img_prompts and wants_pic:
            # Keep her requested subject if the model emitted a vague IMAGE tag
            her_prompt = prompt_from_request(message, fallback="")
            if her_prompt and "photograph" in her_prompt.lower():
                img_prompts = [her_prompt, *img_prompts]
        if img_prompts:
            # Always strip tags once we intend to generate (even if cleaned is empty)
            visible_reply = cleaned
            if dumped or wants_pic:
                visible_reply = strip_unsent_image_claims(visible_reply)
                if dumped or looks_like_image_dump(visible_reply):
                    visible_reply = (
                        "On it — sending him that picture."
                        if room == "private"
                        else "Picture incoming."
                    )
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
                    break
                except Exception as exc:  # noqa: BLE001
                    log.exception("Image generation failed for prompt")
                    image_errors.append(str(exc))

            if image_errors and not image_urls:
                fail = user_facing_image_error(RuntimeError(image_errors[0]))
                leftover = strip_chat_chrome(
                    strip_unsent_image_claims(visible_reply),
                    sub_name=memory.sub_name or "",
                    domme_name=memory.domme_name or "",
                    bot_name=bot_name,
                )
                # She asked for a pic — don't keep "I sent it" fiction if nothing attached
                visible_reply = fail if wants_pic else (f"{leftover}\n\n{fail}".strip() if leftover else fail)
    # Persist a clean conversation (spoken line + visible reply), not the prompt blob
    store.set(
        sid,
        _sanitize_history(
            list(history)
            + [
                {"role": "user", "content": f"{speaker}: {message.strip()}"},
                {"role": "assistant", "content": visible_reply or reply or ""},
            ]
        ),
    )
    if visible_reply:
        store.append_display(
            DisplayMessage(speaker=bot_name, content=visible_reply, room=room)
        )

    if (
        role == "sub"
        and room == "group"
        and wants_to_be_free(message)
        and visible_reply
    ):
        note = (
            f"Lockee asked to be free: “{(message or '').strip()[:160]}”\n"
            "He heard he might earn it — and that we'd talk. "
            "What do you want to do with that? Tease him longer, a task, a short unlock you control?"
        )
        try:
            bridge.inject_private_note(store, note, speaker=bot_name)
        except Exception:  # noqa: BLE001
            log.exception("Could not ping private chat about release ask")

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
