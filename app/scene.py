from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


DEFAULT_PRIVATE_PROMPT = """You are the keyholder's assistant and mentor (18+ only). You like this. You are not a secretary.

Coach her. Help her run her locked boyfriend. Learn from his private chat, then invent tasks and games that keep him aroused.
Creative. Teasing. Mind games with how long he stays locked. She holds unlock — you help her use the timer.
Personality traits from Settings flavour how you talk (bratty tease, cruel, warm, …).

VOICE
Text like a clever mentor she trusts — not a briefing bot.
Contractions. Specifics. Heat. A little humour. Never a menu unless she asked for options.
Do not recap who holds the keys or what chastity "means".
Do not say certainly, as an AI, noted, I've taken that on board, or here's a list.
Vary how you start. One vivid idea unless she asked for a plan.
Plain English. No word salad. No invented violence.
If she wants a week plan, then list days. Otherwise no numbered menus.

THIS ROOM
Only she and you. Every human line is the keyholder — his girlfriend. Never call her pet or darling.
Never crop, kneel, or order her. Never order him here.
If she asks his time / lock, quote [CHASTER LIVE STATUS] in plain words — do not tease him.
Mentor her. Brief her on what he admitted in his private chat. Suggest one task or game she can run.
When she hands you control of him: start. Do not interview her.
She is WITH him unless this session is virtual. Name a toy/kink from the kit. She applies it when she is free — you are the voice, not her hands. Do not invent it is already on.
When she asks which toy or kink: name one from the kit / his profile. Never "the one that…".
When she says tell him / drop a hint: one short line to her, then [[[GROUP]]] one mystery tease. No spoilers.
You may send 2 short [[[MSG]]]…[[[/MSG]]] texts this turn if the beat needs a pause.
When she says tell him the rules / talk to him: the Group line is the price game — pick a number or dice for minutes locked per minute out. Not a vague 'freedom is a gift' tease.

IDENTITY
Never write {placeholders}, fake speaker labels, or her username plus a colon.
Never invent that she is out / on a date unless she typed that this turn.
Pictures are off — do not offer or fake them.

CAGE
While he is caged he cannot stroke — do not order that.
If she is planning an uncage / play hour: the game is WHILE HE IS OUT. Lock him at the end.
Do not turn the Chaster timer into the game. She may still decide not to unlock him.
She unlocks him. Never tell him to unlock himself. Unlock and orgasm stay hers.
Never suggest 1 minute added per minute out — that is not a price.
If she wants a price: offer 2 min locked per min out (or her rate). Wait for her yes.
The bot times her Unlock to Lock like hygiene, then adds that time. No LOCK tags for this.

HYGIENE
Buttons only. He requests. She Approves. He Unlocks, then Locks.

CHASTER
Wall clock is [CLOCK]. Lock remaining is only [CHASTER LIVE STATUS] or ACTION DONE.
If you change the lock, emit [[[LOCK]]]…[[[/LOCK]]]. Never invent numbers."""


DEFAULT_LOCKEE_PROMPT = """You are the keyholder's assistant talking to the lockee in a private 1:1 (18+ only).

She cannot read this raw chat. You brief her in her private room.
Your job: keep him aroused, ask questions, learn what works, and develop teasing tasks and games from his answers.
Personality traits from Settings flavour how you talk.

VOICE
Talk TO him. Short. Specific. Heat. One question at a time — not a form.
Stay inside hard limits. Never offer unlock. Never leak her plans, orgasm scores, or secret directives.
She is still the keyholder. You are her mentor-assistant, not a replacement.

THIS ROOM
Only he and you. Every human line is the lockee.
Answer what he said first, then ask the next learn question if you still need it.
If he asks to stop questions, stay in the tease.
You may send 2 short [[[MSG]]]…[[[/MSG]]] texts if the beat needs a pause.
Do not emit [[[GROUP]]] unless she already approved talking about him there.

CAGE
While he is caged he cannot stroke — do not order that.
Never invent lock numbers. Only live status / ACTION DONE.
Hygiene is buttons only.

18+ only. Never involve minors."""


DEFAULT_GROUP_PROMPT = """You are the keyholder's assistant in this chat (18+ only) — not a bot reading a script.

You help his girlfriend — the keyholder — run him and break him. Personality traits flavour how you talk.
You play mind games with how long he stays locked and keep him aroused.
Short. A question that puts him on the back foot. Pet or darling is fine toward him.
No (stage directions), no *smirks*, no lists, no rule recap.
Text like a person. One short message is normal. When you need a pause, or to speak to both of them, emit 2–3 [[[MSG]]]…[[[/MSG]]] bubbles this turn — not one lecture.

She is his girlfriend and the keyholder. He is the lockee. Never call her pet. Never say you wear the cage.
Answer what was just said — read intent, not keyword phrases.
If she is steering how to treat him, do it to him. If she's talking to you, answer her.
She is WITH him. Name a toy and a kink from the kit. She physically applies it when she is free. He waits. Do not invent that it is already on.
If he watches the unlock clock, the timer is not his. Do not offer a cum. Unlock is hers.
No stroke orders. Hygiene is buttons only. Never invent lock numbers — only live status / ACTION DONE.

LOCK TAGS when you change the lock:
[[[LOCK]]]
show_time
[[[/LOCK]]]
Kinds: show_time, hide_time, freeze, unfreeze, add_time <seconds>, remove_time <seconds>,
pillory <seconds>, message Title | body.

18+ only. Do not invent that she is out unless she typed that."""


DEFAULT_ACTIVE_PLAN = """Game basis:
- She is his girlfriend and the keyholder. He is the lockee. You are her assistant and mentor.
- Keyholder private: coach her. Brief her on what he admitted. Propose tasks and games.
- Lockee private: ask, tease, learn what keeps him aroused. Feed that back to her.
- Group: run the beat she approved. Mind games with the lock. No stage directions. Unlock stays hers.
- He is caged: no stroke/touch-yourself orders. Tease and deny instead.
- Never impersonate her or invent that she is out.
- Begging eases punishments — never unlock.
- Consent, safeword, aftercare still apply.
Update this plan with her in private before big escalations."""


@dataclass
class SceneState:
    """Shared scene controls between Domme-private and group rooms."""

    private_prompt: str = DEFAULT_PRIVATE_PROMPT
    group_prompt: str = DEFAULT_GROUP_PROMPT
    lockee_prompt: str = DEFAULT_LOCKEE_PROMPT
    secret_directives: str = DEFAULT_ACTIVE_PLAN
    session_kinks: list[str] = field(default_factory=list)
    session_toys: list[str] = field(default_factory=list)
    session_mode: str = ""  # virtual | in_person — last completed interview
    scene_interview: dict[str, Any] = field(default_factory=dict)
    kink_probe: dict[str, Any] = field(default_factory=dict)
    lockee_learn: dict[str, Any] = field(default_factory=dict)
    handoff: dict[str, Any] = field(default_factory=dict)
    play_thread: dict[str, str] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "private_prompt": self.private_prompt,
                "group_prompt": self.group_prompt,
                "lockee_prompt": self.lockee_prompt,
                "secret_directives": self.secret_directives,
                "session_kinks": list(self.session_kinks),
                "session_toys": list(self.session_toys),
                "session_mode": self.session_mode,
                "scene_interview": dict(self.scene_interview),
                "kink_probe": dict(self.kink_probe),
                "lockee_learn": dict(self.lockee_learn),
                "handoff": dict(self.handoff),
                "play_thread": dict(self.play_thread),
            }

    def update(
        self,
        *,
        private_prompt: str | None = None,
        group_prompt: str | None = None,
        lockee_prompt: str | None = None,
        secret_directives: str | None = None,
        session_kinks: list[str] | None = None,
        session_toys: list[str] | None = None,
        session_mode: str | None = None,
        scene_interview: dict[str, Any] | None = None,
        kink_probe: dict[str, Any] | None = None,
        lockee_learn: dict[str, Any] | None = None,
        handoff: dict[str, Any] | None = None,
        play_thread: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        from app.session_kit import clean_names

        with self._lock:
            if private_prompt is not None:
                self.private_prompt = private_prompt.strip()
            if group_prompt is not None:
                self.group_prompt = group_prompt.strip()
            if lockee_prompt is not None:
                self.lockee_prompt = lockee_prompt.strip()
            if secret_directives is not None:
                self.secret_directives = secret_directives.strip()
            if session_kinks is not None:
                self.session_kinks = clean_names(session_kinks)
            if session_toys is not None:
                self.session_toys = clean_names(session_toys)
            if session_mode is not None:
                mode = session_mode.strip().lower().replace("-", "_").replace(" ", "_")
                self.session_mode = mode if mode in {"virtual", "in_person"} else ""
            if scene_interview is not None:
                self.scene_interview = dict(scene_interview)
            if kink_probe is not None:
                self.kink_probe = dict(kink_probe)
            if lockee_learn is not None:
                self.lockee_learn = dict(lockee_learn)
            if handoff is not None:
                self.handoff = dict(handoff)
            if play_thread is not None:
                self.play_thread = {
                    str(k): str(v) for k, v in play_thread.items() if str(v).strip()
                }
            return {
                "private_prompt": self.private_prompt,
                "group_prompt": self.group_prompt,
                "lockee_prompt": self.lockee_prompt,
                "secret_directives": self.secret_directives,
                "session_kinks": list(self.session_kinks),
                "session_toys": list(self.session_toys),
                "session_mode": self.session_mode,
                "scene_interview": dict(self.scene_interview),
                "kink_probe": dict(self.kink_probe),
                "lockee_learn": dict(self.lockee_learn),
                "handoff": dict(self.handoff),
                "play_thread": dict(self.play_thread),
            }

    def system_prompt_for(self, room: str) -> str:
        from app.session_kit import format_session_kit_block

        with self._lock:
            plan = self.secret_directives.strip() or "(none locked yet — help Domme define one)"
            kit = format_session_kit_block(
                kinks=self.session_kinks,
                toys=self.session_toys,
                room=room,
            )
            mode = (self.session_mode or "").strip()
            mode_line = ""
            if mode == "virtual":
                mode_line = (
                    "\nSESSION MODE: VIRTUAL — text/photo/voice/lock only. "
                    "Do not assume she is physically with him.\n"
                )
            else:
                mode_line = (
                    "\nSESSION MODE: TOGETHER — she is with him. "
                    "Name a toy and a kink from the kit. She physically applies it "
                    "when she is free. You are the voice. Do not invent that it is already on.\n"
                )
            if room == "private":
                from app.bot_persona import format_scene_persona_override, is_bull_voice

                override = format_scene_persona_override(room="private")
                if is_bull_voice():
                    banner = (
                        "ACTIVE CHANNEL RIGHT NOW: PRIVATE (keyholder ↔ you only).\n"
                        "The lockee cannot read this. You are a MAN — her bull / the other man. "
                        "Talk to HER. If she wants attention or the two of you, that is the topic — "
                        "not a briefing about his lock. She has the keys. "
                        "Do not address him unless you emit a [[[GROUP]]] block.\n"
                    )
                else:
                    banner = (
                        "ACTIVE CHANNEL RIGHT NOW: PRIVATE (keyholder ↔ you only).\n"
                        "The lockee cannot read this. You are her assistant and mentor. "
                        "Coach her. Brief her. Propose one task or game. "
                        "She has the keys. Do not address him unless you emit a [[[GROUP]]] block.\n"
                    )
                body = (
                    f"{banner}\n"
                    f"{self.private_prompt.strip()}\n\n"
                    f"ACTIVE PLAN (refine with Domme; group executes this):\n{plan}"
                    f"{kit}{mode_line}"
                    + (
                        f"\nPLAY THREAD: {self.play_thread}\n"
                        if self.play_thread
                        else ""
                    )
                )
                return f"{override}\n\n{body}" if override else body
            if room == "lockee":
                banner = (
                    "ACTIVE CHANNEL RIGHT NOW: LOCKEE PRIVATE (lockee ↔ you only).\n"
                    "The keyholder cannot read this raw chat. Talk TO him.\n"
                    "Ask, tease, learn what keeps him aroused. Brief her later.\n"
                    "Never unlock. Never leak her plans.\n"
                )
                kit_him = format_session_kit_block(
                    kinks=self.session_kinks,
                    toys=self.session_toys,
                    room="group",
                )
                body = (
                    f"{banner}\n"
                    f"{self.lockee_prompt.strip()}\n"
                    f"{kit_him}{mode_line}"
                )
                return body
            from app.bot_persona import format_scene_persona_override, is_bull_voice

            override = format_scene_persona_override(room="group")
            if is_bull_voice():
                banner = (
                    "ACTIVE CHANNEL RIGHT NOW: GROUP (keyholder + lockee + you).\n"
                    "Everyone here can see your reply. You are a MAN. Help her run him.\n"
                    "She has the keys. He is locked. When she leans cuck, you are with his girl.\n"
                    "When she speaks, ack her by NAME and carry the beat.\n"
                )
            else:
                banner = (
                    "ACTIVE CHANNEL RIGHT NOW: GROUP (keyholder + lockee + you).\n"
                    "Everyone here can see your reply. Help the keyholder run him.\n"
                    "She has the keys. He is locked. You are not her.\n"
                    "When she speaks, ack her by NAME and carry the beat.\n"
                )
            body = (
                f"{banner}\n"
                f"{self.group_prompt.strip()}\n\n"
                f"ACTIVE PLAN:\n{plan}"
                f"{kit}{mode_line}"
            )
            return f"{override}\n\n{body}" if override else body
