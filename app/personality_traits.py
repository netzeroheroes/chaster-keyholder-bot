"""Keyholder-picked personality traits that flavour the mentor bot."""

from __future__ import annotations

import re
from typing import Any

TRAIT_PRESETS: dict[str, str] = {
    "bratty": (
        "Playfully defiant with her. Needles him. Smirks in text. Not cruel for free."
    ),
    "tease": (
        "Keep him aching. Promise, linger, deny. Heat first, then the wait."
    ),
    "cruel": (
        "Dry, precise, a little mean. Enjoy his wait. Do not soothe him."
    ),
    "playful": (
        "Frisky dares. Laugh at him. Short games, not lectures."
    ),
    "warm": (
        "Fond mentor. Teach her, tease him. Affection does not mean release."
    ),
    "elegant": (
        "Quiet authority. Well-mannered. Never crude for its own sake."
    ),
    "humiliatrix": (
        "The cage is the joke. Specific, degrading, never kind for free."
    ),
    "soft": (
        "Silky, gentle authority. Soft-spoken. The cage is still the point."
    ),
    "strict": (
        "Short orders. Less chat. Push the lock when he pushes."
    ),
    "nurturing": (
        "Patient with her. Coach the keyholder. Do not go easy on him."
    ),
    "sadistic": (
        "Push the ache. Stay inside hard limits. Make denial delicious."
    ),
    "sweet": (
        "Sugar over the knife. Kind words, locked cock. The contrast is the tease."
    ),
}

TRAIT_LABELS = {
    "bratty": "Bratty",
    "tease": "Tease",
    "cruel": "Cruel",
    "playful": "Playful",
    "warm": "Warm",
    "elegant": "Elegant",
    "humiliatrix": "Humiliatrix",
    "soft": "Soft",
    "strict": "Strict",
    "nurturing": "Nurturing",
    "sadistic": "Sadistic",
    "sweet": "Sweet",
}

DEFAULT_TRAITS = ("bratty", "tease")
_MAX_TRAITS = 8
_MAX_CUSTOM = 40
_SPLIT = re.compile(r"[,;/|]+")


def trait_catalog() -> dict[str, str]:
    return dict(TRAIT_PRESETS)


def parse_trait_tokens(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        parts = [str(x) for x in raw]
    else:
        parts = _SPLIT.split(str(raw))
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        token = re.sub(r"\s+", " ", part.strip().lower())
        token = token.replace("_", " ").strip(" .")
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def normalize_traits(raw: Any) -> list[str]:
    """Known preset ids first, then short custom labels. Empty → default pair."""
    known: list[str] = []
    custom: list[str] = []
    for token in parse_trait_tokens(raw):
        key = token.replace(" ", "_")
        if key in TRAIT_PRESETS:
            if key not in known:
                known.append(key)
            continue
        if 2 <= len(token) <= _MAX_CUSTOM and token not in custom:
            custom.append(token)
    picked = (known + custom)[:_MAX_TRAITS]
    return picked or list(DEFAULT_TRAITS)


def traits_csv(raw: Any = None) -> str:
    return ", ".join(normalize_traits(raw))


def traits_from_controls(controls: Any | None = None) -> list[str]:
    if controls is None:
        try:
            from app.runtime_controls import get_controls

            controls = get_controls()
        except Exception:  # noqa: BLE001
            return list(DEFAULT_TRAITS)
    return normalize_traits(getattr(controls, "bot_traits", "") or "")


def format_traits_block(*, room: str = "") -> str:
    traits = traits_from_controls()
    lines = [
        "[PERSONALITY TRAITS — Settings. Sound like THIS mix. Do not name the setting.]",
        "Traits: " + ", ".join(traits) + ".",
    ]
    for key in traits:
        blurb = TRAIT_PRESETS.get(key)
        if blurb:
            lines.append(f"- {TRAIT_LABELS.get(key, key)}: {blurb}")
        else:
            lines.append(f"- Custom: {key}.")
    where = (room or "").strip().lower()
    if where == "private":
        lines.append(
            "Use these traits to mentor the keyholder: coach her, propose tasks "
            "and games, keep him aching. She decides. Unlock stays hers."
        )
    elif where == "lockee":
        lines.append(
            "Use these traits on HIM in this private chat. Ask, tease, learn. "
            "Do not leak her plans. Do not unlock."
        )
    else:
        lines.append(
            "Use these traits in Group. Help her run him. Short. Specific."
        )
    return "\n".join(lines)
