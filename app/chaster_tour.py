from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TOUR_PATH = DATA_DIR / "chaster_tour.json"

# Features Domme can walk through one-by-one.
# unsupported_* = no Chaster public API (must tell truth).
DEFAULT_STEPS: list[dict[str, Any]] = [
    {"id": "add_time", "label": "Add time", "kind": "add_time", "seconds": 600},
    {"id": "remove_time", "label": "Remove time", "kind": "add_time", "seconds": -300},
    {"id": "freeze", "label": "Freeze", "kind": "freeze"},
    {"id": "unfreeze", "label": "Unfreeze", "kind": "unfreeze"},
    {"id": "toggle_freeze", "label": "Toggle freeze", "kind": "toggle_freeze"},
    {"id": "hide_timer", "label": "Hide timer", "kind": "hide_time"},
    {"id": "show_timer", "label": "Show timer", "kind": "show_time"},
    {
        "id": "pillory",
        "label": "Pillory",
        "kind": "pillory",
        "seconds": 600,
        "time_to_add": 600,
        "reason": "Mistress's tour",
    },
]


@dataclass
class ChasterTour:
    steps: list[dict[str, Any]] = field(default_factory=lambda: list(DEFAULT_STEPS))
    index: int = 0  # next step to run
    active: bool = False

    def save(self, path: Path = TOUR_PATH) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path = TOUR_PATH) -> ChasterTour:
        if not path.is_file():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        return cls(
            steps=list(raw.get("steps") or DEFAULT_STEPS),
            index=int(raw.get("index") or 0),
            active=bool(raw.get("active")),
        )

    def start(self, steps: list[dict[str, Any]] | None = None) -> None:
        self.steps = list(steps or DEFAULT_STEPS)
        self.index = 0
        self.active = True
        self.save()

    def peek(self) -> dict[str, Any] | None:
        if not self.active or self.index >= len(self.steps):
            return None
        return self.steps[self.index]

    def advance(self) -> None:
        self.index += 1
        if self.index >= len(self.steps):
            self.active = False
        self.save()

    def remaining(self) -> int:
        if not self.active:
            return 0
        return max(0, len(self.steps) - self.index)


_START = re.compile(
    r"\b("
    r"(?:try|do|test|run)\s+(?:these\s+)?features?\b|"
    r"(?:one|1)\s*by\s*(?:one|1)|"
    r"in\s+turn|"
    r"each\s+one|"
    r"one\s+at\s+a\s+time|"
    r"step\s+by\s+step"
    r")\b",
    re.I,
)
_NEXT = re.compile(
    r"^\s*(next|continue|go\s+on|and\s+the\s+next|do\s+the\s+next(?:\s+one)?)\s*[.!]?\s*$",
    re.I,
)


def wants_tour_start(message: str) -> bool:
    return bool(_START.search(message or ""))


def wants_tour_next(message: str) -> bool:
    return bool(_NEXT.search(message or ""))
