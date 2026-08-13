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
) -> str:
    """Human-readable speaker tag used in UI + model context."""
    base = SPEAKER[role]
    handle = (chaster_username or "").strip().lstrip("@")
    if handle:
        return f"{base} (@{handle})"
    if memory is None:
        return base
    if role == "domme":
        name = (memory.domme_name or "").strip()
        title = (memory.domme_title or "").strip()
        bits = [b for b in (name, title) if b]
        return f"{base} ({' / '.join(bits)})" if bits else base
    name = (memory.sub_name or "").strip()
    return f"{base} ({name})" if name else base


def bot_label(memory: LongTermMemory | None = None) -> str:
    name = ((memory.bot_name if memory else "") or "").strip() or "Keyholder"
    return name


def format_user_line(
    role: Role,
    message: str,
    memory: LongTermMemory | None = None,
    *,
    chaster_role: str | None = None,
    chaster_username: str | None = None,
) -> str:
    label = speaker_label(role, memory, chaster_username=chaster_username)
    if role == "domme":
        who = "human Domme / Chaster keyholder"
    else:
        who = "human Sub / Chaster wearer (lockee)"
    chaster_bit = ""
    cr = (chaster_role or "").strip().lower()
    handle = (chaster_username or "").strip().lstrip("@")
    if cr or handle:
        bits = [b for b in (cr or None, f"@{handle}" if handle else None) if b]
        chaster_bit = f" Chaster identity: {', '.join(bits)}."
    return (
        f"[{label}]: {message}\n"
        f"[IDENTITY: This message is from the {who}.{chaster_bit} "
        f"You are the AI Domme/keyholder — a separate person. "
        f"Never confuse yourself with {SPEAKER[role]} or speak as if you are them.]"
    )
