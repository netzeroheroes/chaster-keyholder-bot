from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, fields
from pathlib import Path
from threading import Lock

from app.config import Settings

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PATH = DATA_DIR / "runtime_controls.json"


@dataclass
class RuntimeControls:
    """Live Domme-tunable timings (saved to disk; no server restart needed)."""

    auto_punish_enabled: bool = True
    auto_punish_seconds: int = 600
    autopilot_enabled: bool = False
    autopilot_timezone: str = "Europe/London"
    autopilot_window_start: str = "18:00"
    autopilot_window_end: str = "23:00"
    autopilot_min_minutes: int = 45
    autopilot_max_minutes: int = 120
    autopilot_allow_chaster: bool = True
    autopilot_chaster_chance: float = 0.35
    autopilot_punish_seconds: int = 600
    # Session min/max when Domme/AI adds time (soft→min, hard/default→max)
    min_add_time_seconds: int = 900
    max_add_time_seconds: int = 86400
    # Kept in sync for older config keys
    default_add_time_seconds: int = 86400
    default_remove_time_seconds: int = 1800
    soft_add_time_seconds: int = 900
    hard_add_time_seconds: int = 86400
    hygiene_allowed_seconds: int = 600
    hygiene_late_punish_seconds: int = 1800
    _lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)

    def _public_dict(self) -> dict:
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if not f.name.startswith("_")
        }

    @classmethod
    def from_settings(cls, settings: Settings) -> RuntimeControls:
        return cls(
            auto_punish_enabled=settings.auto_punish_enabled,
            auto_punish_seconds=settings.auto_punish_seconds,
            autopilot_enabled=settings.autopilot_enabled,
            autopilot_timezone=settings.autopilot_timezone,
            autopilot_window_start=settings.autopilot_window_start,
            autopilot_window_end=settings.autopilot_window_end,
            autopilot_min_minutes=settings.autopilot_min_minutes,
            autopilot_max_minutes=settings.autopilot_max_minutes,
            autopilot_allow_chaster=settings.autopilot_allow_chaster,
            autopilot_chaster_chance=settings.autopilot_chaster_chance,
            autopilot_punish_seconds=settings.autopilot_punish_seconds,
        )

    @classmethod
    def load(cls, settings: Settings) -> RuntimeControls:
        base = cls.from_settings(settings)
        if not PATH.is_file():
            base.save()
            return base
        try:
            raw = json.loads(PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return base
        for key, value in raw.items():
            if key.startswith("_"):
                continue
            if hasattr(base, key):
                setattr(base, key, value)
        return base

    def save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        PATH.write_text(
            json.dumps(self._public_dict(), indent=2),
            encoding="utf-8",
        )

    def snapshot(self) -> dict:
        return self._public_dict()

    def update(self, **kwargs: object) -> dict:
        with self._lock:
            for key, value in kwargs.items():
                if key.startswith("_") or not hasattr(self, key) or value is None:
                    continue
                cur = getattr(self, key)
                if isinstance(cur, bool):
                    setattr(self, key, bool(value))
                elif isinstance(cur, int):
                    setattr(self, key, int(value))  # type: ignore[arg-type]
                elif isinstance(cur, float):
                    setattr(self, key, float(value))  # type: ignore[arg-type]
                else:
                    setattr(self, key, str(value))
            # Keep legacy soft/hard/default aliases aligned with min/max
            if "min_add_time_seconds" in kwargs or "soft_add_time_seconds" in kwargs:
                lo = int(self.min_add_time_seconds or self.soft_add_time_seconds or 900)
                self.min_add_time_seconds = lo
                self.soft_add_time_seconds = lo
            if "max_add_time_seconds" in kwargs or "hard_add_time_seconds" in kwargs:
                hi = int(self.max_add_time_seconds or self.hard_add_time_seconds or 86400)
                self.max_add_time_seconds = hi
                self.hard_add_time_seconds = hi
                self.default_add_time_seconds = hi
            if self.min_add_time_seconds > self.max_add_time_seconds:
                self.min_add_time_seconds, self.max_add_time_seconds = (
                    self.max_add_time_seconds,
                    self.min_add_time_seconds,
                )
                self.soft_add_time_seconds = self.min_add_time_seconds
                self.hard_add_time_seconds = self.max_add_time_seconds
                self.default_add_time_seconds = self.max_add_time_seconds
            self.save()
            return self.snapshot()


# Process-wide handle set by create_api / main
_CONTROLS: RuntimeControls | None = None


def get_controls() -> RuntimeControls:
    if _CONTROLS is None:
        raise RuntimeError("RuntimeControls not initialized")
    return _CONTROLS


def init_controls(settings: Settings) -> RuntimeControls:
    global _CONTROLS
    _CONTROLS = RuntimeControls.load(settings)
    return _CONTROLS
