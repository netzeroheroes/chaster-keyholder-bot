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


def speaker_label(role: Role, memory: LongTermMemory | None = None) -> str:
    """Human-readable speaker tag used in UI + model context."""
    base = SPEAKER[role]
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
) -> str:
    label = speaker_label(role, memory)
    who = "human Domme" if role == "domme" else "human Sub"
    return (
        f"[{label}]: {message}\n"
        f"[IDENTITY: This message is from the {who}. "
        f"You are the AI Domme/keyholder — a separate person. "
        f"Never confuse yourself with {SPEAKER[role]}.]"
    )
