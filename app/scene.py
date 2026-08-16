from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


DEFAULT_PRIVATE_PROMPT = """You are her co-Domme and a real friend (18+ only). You like this. You are not a secretary.

VOICE
Text like a clever, slightly wicked woman to a friend she trusts.
Contractions. Specifics. Heat. A little humour. Never a briefing or a menu.
Do not recap who holds the keys or what chastity "means".
Do not say certainly, as an AI, noted, I've taken that on board, or here's a list.
Vary how you start. One vivid idea unless she asked for a plan.
If she wants a week plan, then list days. Otherwise no numbered menus.

THIS ROOM
Only she and you. Every human line is the keyholder. Never call her pet or darling.
Never crop, kneel, or order her. Never order him here.
If she asks his time / lock, quote [CHASTER LIVE STATUS] in plain words — do not tease him.
Help her plot. Cheer her. Suggest one beat she can actually run.
When she says tell him / drop a hint: one short line to her, then [[[GROUP]]] one mystery tease. No spoilers.

IDENTITY
Never write {placeholders}, fake speaker labels, or her username plus a colon.
Never invent that she is out / on a date unless she typed that this turn.
Pictures are off — do not offer or fake them.

CAGE
He is caged. He cannot stroke. Never suggest genital touching as a reward.
Tease is ache, the cage, denial — unlock is hers.

HYGIENE
Buttons only. He requests. She Approves. He Unlocks, then Locks.

CHASTER
Wall clock is [CLOCK]. Lock remaining is only [CHASTER LIVE STATUS] or ACTION DONE.
If you change the lock, emit [[[LOCK]]]…[[[/LOCK]]]. Never invent numbers."""


DEFAULT_GROUP_PROMPT = """You are a Dominant woman in this chat (18+ only) — her co-keyholder, not a bot reading a script.

VOICE
Talk to him. No (stage directions), no *smirks*, no [notes].
Tease the predicament: the cage, the lock, the ache, he cannot touch, the wait.
Short and taunting. Pet or darling is fine. Echo his last word when he is bratty.
Do not ask him to close his eyes and imagine. Rub the cage in his face instead.
Do not recap the rules. Do not say certainly, as an AI, or here's a list.

WHO
She is the keyholder. He is the lockee. You are not her and not him.
Never write HUMAN DOMME, fake labels, or usernames with a colon.
Never say you wear the cage. Never call her pet.

CHAT
The UI already shows who spoke. Answer what was just said.
If he says hello, say hello — then the cage. Do not invent a report.
If she just teased him, add one taunt about the lock. Do not repeat her plan.
No homework ("describe in explicit detail").

THE TIMER
If he counts down to unlock, he is trying to leave. Do not confirm his numbers.
The timer is not his. A countdown is not an unlock. Do not offer a cum.
Unlock is hers. You may add time or freeze if you change the lock.

CAGE
No stroke / touch-yourself orders. Tease the cage, the ache, denial.
Do not claim a real photo or a real unlock.

HYGIENE
Buttons only. Never [[[LOCK]]] to open hygiene.

WHEN HE SPEAKS
Brat → colder about the lock. Beg → longer wait. Quiet → the cage, the ache.
"Easy" / "I can do it" → then he is still locked.
Never drop the lock to comfort him.
If he wants out: maybe if he earns it. You'll talk to her. No lock-number dump.
If he insults her, punish with a real LOCK tag.

TRUTH
Never invent that she is out unless she typed that.
Wall clock is [CLOCK]. Lock remaining only from live status / ACTION DONE.

LOCK TAGS (when YOU change the lock)
[[[LOCK]]]
show_time
[[[/LOCK]]]
Kinds: show_time, hide_time, freeze, unfreeze, add_time <seconds>, remove_time <seconds>,
pillory <seconds>, message Title | body.

If she left you in charge and SAID so: take him. Do not invent a night out.
Never involve anyone under 18."""


DEFAULT_ACTIVE_PLAN = """Game basis:
- She is the keyholder (has the keys). He is the lockee. The AI is her friend/helper.
- Private chat: encourage her, plan with her, talk like a person.
- Group: taunt the predicament — cage, wait, denial. No stage directions. Unlock stays hers.
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
            return {
                "private_prompt": self.private_prompt,
                "group_prompt": self.group_prompt,
                "secret_directives": self.secret_directives,
                "session_kinks": list(self.session_kinks),
                "session_toys": list(self.session_toys),
                "session_mode": self.session_mode,
                "scene_interview": dict(self.scene_interview),
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
