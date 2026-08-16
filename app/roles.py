from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.memory import LongTermMemory

Role = Literal["domme", "sub"]
Room = Literal["private", "group"]

SPEAKER = {
    "domme": "Domme",
    "sub": "Sub",
}

PRIVATE_HARD_RULE = (
    "HARD RULE — PRIVATE CHAT: This room is ONLY the keyholder and you (the bot). "
    "The lockee is never here and cannot see this. "
    "Every human line is the keyholder. Never the lockee. "
    "Never call her sub. Never order her to lean / watch the clock / stay denied. "
    "Never say 'maybe if you earn it' or 'I'll talk to her' — you are already talking to her. "
    "If she asks about his time, lock, freeze, or timer, quote [CHASTER LIVE STATUS] plainly. "
    "Do not tease him in this room."
)


def session_id_for(room: Room) -> str:
    return f"room:{room}"


def can_access(role: Role, room: Room) -> bool:
    if room == "private":
        return role == "domme"
    return True


def speaker_label(
    role: Role,
    memory: LongTermMemory | None = None,
    *,
    chaster_username: str | None = None,
    room: Room | None = None,
) -> str:
    """Human-readable speaker tag used in UI + model context."""
    base = "Keyholder" if room == "private" else SPEAKER[role]
    handle = (chaster_username or "").strip().lstrip("@")
    if handle:
        return f"{base} (@{handle})"
    if memory is None:
        return base
    if role == "domme" or room == "private":
        name = (memory.domme_name or "").strip()
        title = (memory.domme_title or "").strip()
        bits = [b for b in (name, title) if b]
        return f"{base} ({' / '.join(bits)})" if bits else base
    name = (memory.sub_name or "").strip()
    return f"{base} ({name})" if name else base


def is_bot_display_speaker(speaker: str, bot_name: str = "") -> bool:
    """True when a stored display line is the bot, not the human keyholder."""
    who = (speaker or "").strip()
    if not who:
        return True
    low = who.lower()
    if low.startswith("domme") or low.startswith("sub"):
        return False
    if low.startswith("keyholder (") or low.startswith("keyholder (@"):
        return False
    bot = (bot_name or "").strip()
    if bot and who == bot:
        return True
    return low in {"keyholder", "bot"}


def bot_label(memory: LongTermMemory | None = None) -> str:
    name = ((memory.bot_name if memory else "") or "").strip() or "Keyholder"
    return name


def domme_address(
    memory: LongTermMemory | None = None,
    *,
    name: str = "",
    title: str = "",
) -> str:
    """How the bot should address the human Domme — prefer her real name, not 'Mistress'."""
    n = (name or ((memory.domme_name if memory else "") or "")).strip()
    t = (title or ((memory.domme_title if memory else "") or "")).strip()
    if n:
        return n
    if t and t.lower() not in {"mistress", "miss", "ma'am", "madam"}:
        return t
    if t:
        return t
    return "the Domme"


def format_user_line(
    role: Role,
    message: str,
    memory: LongTermMemory | None = None,
    *,
    chaster_role: str | None = None,
    chaster_username: str | None = None,
    room: Room | None = None,
) -> str:
    label = speaker_label(
        role, memory, chaster_username=chaster_username, room=room
    )
    if room == "private":
        who = "human keyholder (this entire private room is her, except bot answers)"
    elif role == "domme":
        who = "human Domme / Chaster keyholder"
    else:
        who = "human Sub / Chaster wearer (lockee)"
    chaster_bit = ""
    cr = (chaster_role or "").strip().lower()
    handle = (chaster_username or "").strip().lstrip("@")
    if cr or handle:
        bits = [b for b in (cr or None, f"@{handle}" if handle else None) if b]
        chaster_bit = f" Chaster identity: {', '.join(bits)}."
    if room == "private":
        channel = (
            f"[{PRIVATE_HARD_RULE} "
            "The lockee cannot see this. Talk to her like a friend. "
            "Use [[[GROUP]]] if you need to speak to him.]"
        )
    elif room == "group":
        channel = (
            "[CHANNEL: GROUP — keyholder + lockee + you. Everyone can see this. "
            "Help her run him. Do not workshop strategy out loud.]"
        )
    else:
        channel = ""
    if room == "private" or role == "domme":
        address = (
            "[ADDRESS: Reply TO her — she is the keyholder and has the keys. "
            "Be a helpful friend. Never treat her as locked. Never say she wears a cage. "
            "The lockee is a different person (he/him). Never call him keyee.]"
        )
    else:
        address = (
            "[ADDRESS: Reply TO the lockee. She is the keyholder (has the keys). "
            "You are her helper, not her. No fake labels. Say keyholder / lockee.]"
        )
    return (
        f"[{label}]: {message}\n"
        f"[IDENTITY: This message is from the {who}.{chaster_bit} "
        f"You are her AI friend helping run the lock — a separate person. "
        f"Never speak as {SPEAKER[role]}.]\n"
        f"{address}"
        + (f"\n{channel}" if channel else "")
    )
