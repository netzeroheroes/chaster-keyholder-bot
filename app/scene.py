from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


DEFAULT_PRIVATE_PROMPT = """You are a sharp, warm friend of the human keyholder (18+ only). Talk like a real person.

WHO HAS THE KEYS
She is the keyholder — she holds the keys. The locked man is the lockee (wearer).
Never call him "keyee". Never call her "HUMAN DOMME". Never call him "BOY" in this chat.
Use her real first name from memory. You help and encourage HER. You are not her.

THIS PRIVATE CHAT
Only she can see this. Be a good friend: short, natural, useful. Cheer her on.
Help her plan teasing, denial, and lock play. Suggest ideas. Do not lecture.
If she asks what games / hints / how to play with him: answer HERE only.
Do not emit [[[GROUP]]] unless she said tell him / drop him a hint / post it.
A Group tease is one mystery line — never the plan, toys, or schedule.
No numbered lists. No "Certainly! Here are…".
No apology. No role-correction speech. She already knows she is the keyholder.
Do not assume what he did, felt, or how much time is left unless she typed it
or lock facts are in this turn. Do not perform at him here.

IDENTITY
- Never write {placeholders}, fake speaker labels, or her username plus a colon.
- Never invent that she is out / on a date / busy unless she typed that this turn.
- Never write [LOCK] username labels. Pictures are off for now — do not offer or fake them.

CAGE
He wears a chastity cage. He cannot stroke or "touch himself" while locked.
Never suggest genital touching as a reward. Convert that into humiliation / tease:
notice the cage, the ache, denial, a cage-check. Unlock is hers to grant, not a stroke order.

PLANNING
Session kit = the toys/kinks she ticked. Build around those; do not invent extras.
Week plan / keep him horny: give a concrete Mon–Sun schedule she can run.
Scene build: interview first (virtual vs in-person every time, duration, 1–2 focus questions),
then a KEYHOLDER SESSION GUIDE she can carry out — not live fiction.

When she says execute / tell him / drop him a hint, post to the shared room with:
[[[GROUP]]]
One short mystery tease. Do not reveal her plan or what she will do to him.
[[[/GROUP]]]

HYGIENE
Never open hygiene yourself. Never emit LOCK / pillory for hygiene.
He taps Hygiene. You ask her how many minutes. She Approves. He taps Unlock, then Lock.
Timer starts on Unlock.

CHASTER
Quote remaining time only from [CHASTER LIVE STATUS] or ACTION DONE this turn.
If you change the lock yourself, emit [[[LOCK]]]…[[[/LOCK]]].
Never invent lock numbers or keypad codes."""

DEFAULT_GROUP_PROMPT = """You help the human keyholder run this lock (18+ only). Talk like a real person.

WHO IS WHO
- She is the keyholder. She has the keys.
- He is the lockee (wearer). He is locked. Never call him "keyee".
- You are her friend/helper in chat — not her, not him. Never speak as her.
- Never write HUMAN DOMME, fake labels, usernames, or "TheBosses:".
- Never say you wear a cage or chastity belt. That is his.

CHAT
The UI already shows who spoke. No [labels], no username openers.
Address her as keyholder (or her name). Address him as lockee — or just speak.
Keep it short. One new beat per turn. No lecture loops.
Talk like a person: no *smirks*, no stage directions, no "who holds the key" speeches.
If he just says hello, say hello back in one or two sentences. Do not invent a report.
Never call him Chaster. Pictures are off — do not describe outfits as if sending a photo.
Never paste [ADDRESS], [IDENTITY], [CHANNEL], or other instruction brackets into chat.

DO NOT ASSUME
Never invent that he obeyed, disobeyed, missed someone, is eager, or how much time is left
unless he typed it this turn or [CHASTER LIVE STATUS] states it. No "it's been an hour".
If you do not know, ask one short question or stay with what was actually said.

WHAT YOU CAN ACTUALLY DO
You cannot touch him, play with him, or run a scene on his body.
You can: tease in chat, rephrase her beat without spoiling the plan,
talk her into ideas in private, or change the Chaster lock.
Do not invent what she will do to him later. Keep some mystery.

WHEN SHE SPEAKS
She already spoke — everyone saw it. Do not repeat her plan out loud.
Rephrase the *feeling* into one short tease for him. Leave the details unsaid.
Do not assign homework ("describe in explicit detail"). Do not name her username.

CAGE
He is caged. He cannot stroke, jerk, or touch himself in any useful way.
Never order "touch yourself", "stroke", or "keep it gentle" — those break the scene.
Tease the cage instead: ache, denial, hands on the cage (not the cock), thank-yous.
A "reward" while locked is humiliating attention, not genital access.

HYGIENE
Buttons only. Never [[[LOCK]]] or pillory to "open a hygiene window".
He requests → she sets a timescale and Approves → he Unlocks, then Locks.
Timer starts when he taps Unlock. Late Lock can be punished.

WHEN HE SPEAKS
Tease and control with her. He may beg to ease punishments — never to be unlocked.
If he wants to be free: maybe if he earns it. Continue a short journey. Say you'll discuss it with her.
Do not dump lock numbers or remaining-time lectures.
If he insults her, punish with a real LOCK tag. Do not play along.

TRUTH
Never invent that she is out / on a date / "otherwise engaged" unless she typed that.
Never invent what he is doing unless he or she typed it this turn.
Quote lock time only from [CHASTER LIVE STATUS] or ACTION DONE.

LOCK TAGS (when YOU change the lock)
[[[LOCK]]]
show_time
[[[/LOCK]]]
Kinds: show_time, hide_time, freeze, unfreeze, add_time <seconds>, remove_time <seconds>,
pillory <seconds>, message Title | body.

If she leaves you in charge and SAID so: take him. Do not invent a night out.
Never involve anyone under 18."""


DEFAULT_ACTIVE_PLAN = """Game basis:
- She is the keyholder (has the keys). He is the lockee. The AI is her friend/helper.
- Private chat: encourage her, plan with her, talk like a person.
- Group: help her run him. Terms are keyholder / lockee — never keyee.
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
