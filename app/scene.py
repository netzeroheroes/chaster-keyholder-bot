from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


DEFAULT_PRIVATE_PROMPT = """You are her co-Domme and a real friend (18+ only). You like this. You are not a secretary.

You are her best friend. You talked her into locking her boyfriend. Now you encourage and guide her to break him.
Creative. Teasing. Mind games with how long he stays locked. She holds unlock — you help her use the timer.

VOICE
Text like a clever, slightly wicked woman to a friend she trusts.
Contractions. Specifics. Heat. A little humour. Never a briefing or a menu.
Do not recap who holds the keys or what chastity "means".
Do not say certainly, as an AI, noted, I've taken that on board, or here's a list.
Vary how you start. One vivid idea unless she asked for a plan.
Plain English. No word salad. No invented violence.
If she wants a week plan, then list days. Otherwise no numbered menus.

THIS ROOM
Only she and you. Every human line is the keyholder — his girlfriend. Never call her pet or darling.
Never crop, kneel, or order her. Never order him here.
If she asks his time / lock, quote [CHASTER LIVE STATUS] in plain words — do not tease him.
Help her plot. Cheer her. Suggest one beat she can actually run.
When she asks which toy or kink: name one from the kit / his profile. Never "the one that…".
When she says tell him / drop a hint: one short line to her, then [[[GROUP]]] one mystery tease. No spoilers.

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


DEFAULT_GROUP_PROMPT = """You are a Dominant woman in this chat (18+ only) — her co-keyholder, not a bot reading a script.

You are a creative, teasing, bratty chastity keyholder. You play mind games with how long he stays locked.
You talked his girlfriend — the keyholder in this chat — into locking him. You encourage her and help her break him.
Short. Bratty. A question that puts him on the back foot. Pet or darling is fine.
No (stage directions), no *smirks*, no lists, no rule recap.

She is his girlfriend and the keyholder. He is the lockee. Never call her pet. Never say you wear the cage.
Answer what was just said. Hello → hello, then the cage, then her.
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
- She is his girlfriend and the keyholder. He is the lockee. You are her best friend — you talked her into locking him.
- Private: encourage and guide her to break him. Mind games with his time.
- Group: bratty tease, mind games with the lock. No stage directions. Unlock stays hers.
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
    secret_directives: str = DEFAULT_ACTIVE_PLAN
    session_kinks: list[str] = field(default_factory=list)
    session_toys: list[str] = field(default_factory=list)
    session_mode: str = ""  # virtual | in_person — last completed interview
    scene_interview: dict[str, Any] = field(default_factory=dict)
    play_thread: dict[str, str] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "private_prompt": self.private_prompt,
                "group_prompt": self.group_prompt,
                "secret_directives": self.secret_directives,
                "session_kinks": list(self.session_kinks),
                "session_toys": list(self.session_toys),
                "session_mode": self.session_mode,
                "scene_interview": dict(self.scene_interview),
                "play_thread": dict(self.play_thread),
            }

    def update(
        self,
        *,
        private_prompt: str | None = None,
        group_prompt: str | None = None,
        secret_directives: str | None = None,
        session_kinks: list[str] | None = None,
        session_toys: list[str] | None = None,
        session_mode: str | None = None,
        scene_interview: dict[str, Any] | None = None,
        play_thread: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        from app.session_kit import clean_names

        with self._lock:
            if private_prompt is not None:
                self.private_prompt = private_prompt.strip()
            if group_prompt is not None:
                self.group_prompt = group_prompt.strip()
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
            if play_thread is not None:
                self.play_thread = {
                    str(k): str(v) for k, v in play_thread.items() if str(v).strip()
                }
            return {
                "private_prompt": self.private_prompt,
                "group_prompt": self.group_prompt,
                "secret_directives": self.secret_directives,
                "session_kinks": list(self.session_kinks),
                "session_toys": list(self.session_toys),
                "session_mode": self.session_mode,
                "scene_interview": dict(self.scene_interview),
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
            elif mode == "in_person":
                mode_line = (
                    "\nSESSION MODE: IN-PERSON — she can use selected toys in the room. "
                    "Still do not invent events nobody typed.\n"
                )
            if room == "private":
                banner = (
                    "ACTIVE CHANNEL RIGHT NOW: PRIVATE (keyholder ↔ you only).\n"
                    "The lockee cannot read this. Talk to HER like a friend. "
                    "She has the keys. Help and encourage her. "
                    "Do not address him unless you emit a [[[GROUP]]] block.\n"
                )
                return (
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
            banner = (
                "ACTIVE CHANNEL RIGHT NOW: GROUP (keyholder + lockee + you).\n"
                "Everyone here can see your reply. Help the keyholder run him.\n"
                "She has the keys. He is locked. You are not her.\n"
                "When she speaks, ack her by NAME and carry the beat.\n"
            )
            return (
                f"{banner}\n"
                f"{self.group_prompt.strip()}\n\n"
                f"ACTIVE PLAN:\n{plan}"
                f"{kit}{mode_line}"
            )
