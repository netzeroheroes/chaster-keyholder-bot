from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from threading import Lock
from typing import Any

from openai.types.chat import ChatCompletionMessageParam


@dataclass
class DisplayMessage:
    speaker: str  # Domme | Sub | Keyholder | Bot
    content: str
    room: str
    image_url: str | None = None
    video_url: str | None = None
    embed_url: str | None = None
    from_bot: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "speaker": self.speaker,
            "content": self.content,
            "room": self.room,
            "image_url": self.image_url,
            "video_url": self.video_url,
            "embed_url": self.embed_url,
            "from_bot": bool(self.from_bot),
        }


class SessionStore:
    """Chat history keyed by session/chat id (persistable)."""

    def __init__(self, max_messages: int = 120) -> None:
        self._max_messages = max_messages
        self._sessions: dict[str, list[ChatCompletionMessageParam]] = defaultdict(list)
        self._display: dict[str, list[DisplayMessage]] = defaultdict(list)
        self._lock = Lock()

    def get(self, session_id: str) -> list[ChatCompletionMessageParam]:
        with self._lock:
            return list(self._sessions[session_id])

    def set(self, session_id: str, messages: list[ChatCompletionMessageParam]) -> None:
        trimmed = [m for m in messages if m.get("role") != "system"]
        if len(trimmed) > self._max_messages:
            trimmed = trimmed[-self._max_messages :]
        with self._lock:
            self._sessions[session_id] = trimmed

    def append_display(self, message: DisplayMessage) -> None:
        with self._lock:
            bucket = self._display[message.room]
            bucket.append(message)
            if len(bucket) > self._max_messages:
                self._display[message.room] = bucket[-self._max_messages :]

    def display_counts(self) -> dict[str, int]:
        with self._lock:
            return {room: len(msgs) for room, msgs in self._display.items()}

    def get_display(self, room: str) -> list[dict[str, Any]]:
        with self._lock:
            return [m.as_dict() for m in self._display[room]]

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def clear_room(self, room: str) -> None:
        session_id = f"room:{room}"
        with self._lock:
            self._sessions.pop(session_id, None)
            self._display.pop(room, None)

    def export_state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "sessions": {k: list(v) for k, v in self._sessions.items()},
                "display": {
                    room: [m.as_dict() for m in msgs]
                    for room, msgs in self._display.items()
                },
            }

    def import_state(
        self,
        sessions: dict[str, list[ChatCompletionMessageParam]],
        display: dict[str, list[DisplayMessage]],
    ) -> None:
        with self._lock:
            self._sessions = defaultdict(list, sessions)
            self._display = defaultdict(list, display)
