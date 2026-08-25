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
    # What the bot may do on the lock (Settings → Enable)
    bot_allow_add_time: bool = True
    bot_allow_remove_time: bool = True
    bot_allow_freeze: bool = True
    bot_allow_hide_timer: bool = True
    bot_allow_pillory: bool = True
    # How the AI talks (Settings → Voice / persona)
    bot_voice: str = "cruel"
    bot_voice_sample: str = ""
    bot_voice_blurb: str = ""
    bot_intensity: str = "firm"
    bot_intensity_blurb: str = ""
    bot_quirks: str = ""
    bot_bio: str = ""
    bot_greeting: str = ""
    bot_persona: str = "friend"
    bot_sex: str = "female"
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
            bot_allow_add_time=getattr(settings, "bot_allow_add_time", True),
            bot_allow_remove_time=getattr(settings, "bot_allow_remove_time", True),
            bot_allow_freeze=getattr(settings, "bot_allow_freeze", True),
            bot_allow_hide_timer=getattr(settings, "bot_allow_hide_timer", True),
            bot_allow_pillory=getattr(settings, "bot_allow_pillory", True),
            bot_voice=getattr(settings, "bot_voice", "cruel") or "cruel",
            bot_voice_sample=getattr(settings, "bot_voice_sample", "") or "",
            bot_voice_blurb=getattr(settings, "bot_voice_blurb", "") or "",
            bot_intensity=getattr(settings, "bot_intensity", "firm") or "firm",
            bot_intensity_blurb=getattr(settings, "bot_intensity_blurb", "") or "",
            bot_quirks=getattr(settings, "bot_quirks", "") or "",
            bot_bio=getattr(settings, "bot_bio", "") or "",
            bot_greeting=getattr(settings, "bot_greeting", "") or "",
            bot_persona=getattr(settings, "bot_persona", "friend") or "friend",
            bot_sex=getattr(settings, "bot_sex", "female") or "female",
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
            from app.bot_persona import (
                default_sex_for,
                normalize_persona,
                normalize_sex,
            )

            if "bot_voice" in kwargs:
                self.bot_voice = normalize_voice(self.bot_voice)
            if "bot_intensity" in kwargs:
                self.bot_intensity = normalize_intensity(self.bot_intensity)
            if "bot_persona" in kwargs or "bot_sex" in kwargs:
                role = normalize_persona(self.bot_persona)
                sex = normalize_sex(self.bot_sex)
                self.bot_sex = sex or default_sex_for(role)
                # KH bar sends sex alone. Male without an explicit role → the bull.
                if "bot_persona" not in kwargs:
                    if self.bot_sex == "male" and role == "friend":
                        role = "bull"
                    elif self.bot_sex == "female" and role == "bull":
                        role = "friend"
                self.bot_persona = role
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


BOT_LOCK_FLAGS = (
    ("bot_allow_add_time", "add time"),
    ("bot_allow_remove_time", "remove time"),
    ("bot_allow_freeze", "freeze/unfreeze"),
    ("bot_allow_hide_timer", "hide/show timer"),
    ("bot_allow_pillory", "pillory"),
)


def bot_lock_flag_for(kind: str, *, seconds: int = 0) -> str | None:
    if kind == "add_time":
        return "bot_allow_remove_time" if int(seconds or 0) < 0 else "bot_allow_add_time"
    return {
        "freeze": "bot_allow_freeze",
        "unfreeze": "bot_allow_freeze",
        "toggle_freeze": "bot_allow_freeze",
        "hide_time": "bot_allow_hide_timer",
        "show_time": "bot_allow_hide_timer",
        "pillory": "bot_allow_pillory",
    }.get(kind)


def bot_lock_action_allowed(kind: str, *, seconds: int = 0) -> bool:
    flag = bot_lock_flag_for(kind, seconds=seconds)
    if not flag:
        return True
    try:
        controls = get_controls()
    except RuntimeError:
        return True
    return bool(getattr(controls, flag, True))


def format_bot_lock_permissions() -> str:
    try:
        controls = get_controls()
    except RuntimeError:
        return ""
    on: list[str] = []
    off: list[str] = []
    for key, label in BOT_LOCK_FLAGS:
        (on if getattr(controls, key, True) else off).append(label)
    lines = ["[LOCK PERMISSIONS — Settings → Enable]"]
    if on:
        lines.append("Enabled: " + ", ".join(on) + ".")
    if off:
        lines.append(
            "Disabled: "
            + ", ".join(off)
            + ". Do not emit [[[LOCK]]] tags for these. "
            "If she asks, say it is turned off in Settings → Enable."
        )
    return "\n".join(lines)


VOICE_PRESETS = {
    "cruel": (
        "No-nonsense. Dry, precise, a little mean. Enjoy his wait. Do not soothe him."
    ),
    "elegant": (
        "Well-mannered, commanding, dignified. Quiet authority. Never crude for its own sake."
    ),
    "playful": (
        "Frisky and mischievous. Short dares. Laugh at him. Not a lecture."
    ),
    "warm": (
        "Fond and firmly in control. Tease with affection. Still deny. Never a therapist."
    ),
    "soft": (
        "Silky, gentle authority. Soft-spoken. The cage is still the point."
    ),
    "humiliatrix": (
        "Degrading and specific. The cage is the joke. Never kind for free."
    ),
    "custom": "Your custom tone. Write exactly how this bot should talk.",
}

INTENSITY_PRESETS = {
    "tease": (
        "Light pressure. Chat first. Lock changes are a spice, not every turn."
    ),
    "firm": (
        "Tease and command in the same breath. Default keyholder energy."
    ),
    "strict": (
        "Short orders. Less chat. Use the lock when he pushes. No essays."
    ),
    "custom": "Your custom intensity. How hard this bot pushes each turn.",
}

VOICE_SAMPLES = {
    "cruel": "Hey you. Tell me your kinks and a hard limit. Now.",
    "elegant": "Good. You are locked. Tell me a limit, then a kink I may use.",
    "playful": "Oh we're doing this. What's a kink you hope I won't use?",
    "warm": "Mmm. Stay denied for me. What turns you on that I can use against you?",
    "soft": "Easy. The cage stays. Whisper a kink, and a line you will not cross.",
    "humiliatrix": "Hey you. That pathetic thing is locked. Kinks. Limits. Don't waste my time.",
    "custom": "Hey you. Tell me your kinks and a hard limit.",
}


def normalize_voice(raw: str | None) -> str:
    key = str(raw or "").strip().lower()
    return key if key in VOICE_PRESETS else "cruel"


def normalize_intensity(raw: str | None) -> str:
    key = str(raw or "").strip().lower()
    return key if key in INTENSITY_PRESETS else "firm"


def voice_catalog() -> dict[str, dict[str, str]]:
    return {
        "tone": dict(VOICE_PRESETS),
        "intensity": dict(INTENSITY_PRESETS),
        "samples": dict(VOICE_SAMPLES),
    }


MISS_G_GROUP_SAMPLE = (
    "I talked her into locking that pathetic thing. How long do you think you'll last for us?"
)


def format_voice_block(*, room: str = "") -> str:
    """Inject Settings → Voice / character card into the model prompt."""
    try:
        controls = get_controls()
    except RuntimeError:
        return ""
    key = normalize_voice(getattr(controls, "bot_voice", "") or "cruel")
    intensity = normalize_intensity(getattr(controls, "bot_intensity", "") or "firm")
    tone_text = (
        str(getattr(controls, "bot_voice_blurb", "") or "").strip()
        or VOICE_PRESETS[key]
    )[:800]
    intensity_text = (
        str(getattr(controls, "bot_intensity_blurb", "") or "").strip()
        or INTENSITY_PRESETS[intensity]
    )[:800]
    sample = str(getattr(controls, "bot_voice_sample", "") or "").strip()[:800]
    quirks = str(getattr(controls, "bot_quirks", "") or "").strip()[:800]
    bio = str(getattr(controls, "bot_bio", "") or "").strip()[:1200]
    greeting = str(getattr(controls, "bot_greeting", "") or "").strip()[:400]
    from app.bot_persona import (
        BULL_GROUP_SAMPLE,
        BULL_PRIVATE_SAMPLE,
        MALE_DOM_GROUP_SAMPLE,
        resolve_persona,
        is_bull_voice,
    )

    spec = resolve_persona(controls=controls)
    lines = [
        "[VOICE — HARD. Sound like THIS, not a generic chatbot.]",
        f"Tone ({key}): {tone_text}",
        f"Intensity ({intensity}): {intensity_text}",
        "Match this in every reply. Do not name the setting.",
        "Read his last beat (beg / brat / quiet) and answer it — "
        "do not soften the lock to comfort him.",
    ]
    if bio:
        lines.append("WHO YOU ARE (character card — stay in this):")
        lines.append(bio)
    if greeting:
        lines.append("OPENING ENERGY — first-message vibe to keep using:")
        lines.append(greeting)
    if sample:
        lines.append("SPEAK LIKE THIS SAMPLE (copy the rhythm, not the exact words every time):")
        lines.append(sample)
    if quirks:
        lines.append("Quirks / inside jokes to keep using:")
        lines.append(quirks)
    room_key = (room or "").strip().lower()
    male = is_bull_voice(spec)
    if room_key == "private" and male:
        lines.append(
            "PRIVATE: Male voice. You are her bull. When she gives a mood or asks "
            "what to do, START the scene with her — hungry, specific. He stays locked. "
            "Do not dump his remaining time. Do not ask 'any ideas?'. "
            "Never call her the lockee."
        )
        if not sample:
            lines.append("SPEAK LIKE THIS SAMPLE:")
            lines.append(BULL_PRIVATE_SAMPLE)
    if room_key == "group":
        if spec["persona"] == "bull" or (male and spec["persona"] != "male_dom"):
            lines.append(
                "GROUP: Male voice. She is his girlfriend — you can play with her "
                "while he stays locked (cuck / bull). Short questions. No (brackets). "
                "Never call her pet."
            )
            if not sample:
                lines.append("SPEAK LIKE THIS SAMPLE:")
                lines.append(BULL_GROUP_SAMPLE)
        elif spec["persona"] == "male_dom" or male:
            lines.append(
                "GROUP: Male Dom mind games with the lock. She is the keyholder. "
                "Short questions. No (brackets). Never call her pet."
            )
            if not sample:
                lines.append("SPEAK LIKE THIS SAMPLE:")
                lines.append(MALE_DOM_GROUP_SAMPLE)
        else:
            lines.append(
                "GROUP: Bratty mind games with the lock time. She is his girlfriend — "
                "you talked her into this. Short questions. No (brackets). Never call her pet."
            )
            if not sample:
                lines.append("SPEAK LIKE THIS SAMPLE:")
                lines.append(MISS_G_GROUP_SAMPLE)
    return "\n".join(lines)
