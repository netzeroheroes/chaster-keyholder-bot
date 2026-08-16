"""Domme session kit: selected kinks/toys + weekly keyholder planning briefs."""

from __future__ import annotations

import re
from typing import Any

# Soft catalog when Chaster isn't linked or the wearer profile is empty.
_FALLBACK_KINKS: list[dict[str, str]] = [
    {"name": "Chastity", "rating": "love"},
    {"name": "Tease and denial", "rating": "love"},
    {"name": "Orgasm control", "rating": "love"},
    {"name": "Edging", "rating": "like"},
    {"name": "Power exchange", "rating": "like"},
    {"name": "Humiliation", "rating": "like"},
    {"name": "Verbal humiliation", "rating": "like"},
    {"name": "Slave training", "rating": "like"},
    {"name": "Service", "rating": "like"},
    {"name": "Cuckolding", "rating": "curious"},
    {"name": "Spanking", "rating": "like"},
    {"name": "Impact play", "rating": "like"},
    {"name": "Restraints", "rating": "like"},
    {"name": "Gags", "rating": "like"},
    {"name": "Sensory deprivation", "rating": "like"},
    {"name": "Blindfolds", "rating": "like"},
    {"name": "Anal play", "rating": "like"},
    {"name": "Nipple play", "rating": "like"},
    {"name": "Wax play", "rating": "curious"},
    {"name": "SPH", "rating": "curious"},
]

_FALLBACK_TOYS: list[str] = [
    "Blindfold",
    "Collar",
    "Leash",
    "Ball gag",
    "Rope",
    "Leather paddle",
    "Flogger",
    "Crop",
    "Plug",
    "Nipple clamps",
    "Spreader bar",
    "Hood",
    "Wartenberg wheel",
    "Humbler",
    "Ice cubes",
]

_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

_WEEK_PLAN_RE = re.compile(
    r"\b("
    r"plan(?:\s+out)?\s+(?:the|this|his|our)\s+week|"
    r"weekly\s+plan|"
    r"week(?:ly)?\s+(?:schedule|agenda|calendar)|"
    r"schedule\s+(?:the|this|his)\s+week|"
    r"plan\s+(?:a\s+)?week\s+of|"
    r"keep\s+him\s+(?:horny|needy|desperate|denied|submissive|obedient|locked)|"
    r"keep\s+(?:the\s+)?sub\s+(?:horny|needy|desperate|denied|submissive)|"
    r"how\s+do\s+i\s+keep\s+him|"
    r"week\s+of\s+(?:tease|denial|chastity)"
    r")\b",
    re.I,
)

_HORNY_HINT_RE = re.compile(
    r"\b("
    r"keep\s+him\s+(?:on\s+edge|locked|wanting)|"
    r"ideas?\s+to\s+keep\s+him|"
    r"how\s+to\s+keep\s+him"
    r")\b",
    re.I,
)


def clean_names(items: list[Any] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = str(item or "").strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _item_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name") or "").strip()
    return str(item or "").strip()


def _item_rating(item: Any) -> str:
    if isinstance(item, dict):
        rating = str(item.get("rating") or "other").strip().lower()
        if rating in {"love", "like", "curious"}:
            return rating
    return "other"


def normalize_catalog(
    profile: dict[str, Any] | None,
    *,
    username: str = "",
    source: str = "chaster",
) -> dict[str, Any]:
    """Flatten a Chaster kink profile (or fallback) into UI-ready lists."""
    raw = profile if isinstance(profile, dict) else {}
    kinks_in = list(raw.get("kinks") or [])
    toys_in = list(raw.get("toys") or [])

    kinks: list[dict[str, str]] = []
    seen_k: set[str] = set()
    for item in kinks_in:
        name = _item_name(item)
        key = name.lower()
        if not name or key in seen_k:
            continue
        seen_k.add(key)
        kinks.append({"name": name, "rating": _item_rating(item)})

    toys: list[dict[str, str]] = []
    seen_t: set[str] = set()
    for item in toys_in:
        name = _item_name(item)
        key = name.lower()
        if not name or key in seen_t:
            continue
        seen_t.add(key)
        toys.append({"name": name})

    kink_fallback = False
    toy_fallback = False
    if not kinks:
        kinks = [dict(k) for k in _FALLBACK_KINKS]
        kink_fallback = True
    if not toys:
        toys = [{"name": n} for n in _FALLBACK_TOYS]
        toy_fallback = True
    if kink_fallback and toy_fallback:
        source_out = "fallback"
    elif kink_fallback or toy_fallback:
        source_out = "mixed"
    else:
        source_out = source

    rating_rank = {"love": 0, "like": 1, "curious": 2, "other": 3}
    kinks.sort(key=lambda k: (rating_rank.get(k["rating"], 9), k["name"].lower()))
    toys.sort(key=lambda t: t["name"].lower())

    return {
        "username": (username or "").strip(),
        "source": source_out,
        "bio": str(raw.get("bio") or "").strip(),
        "kinks": kinks,
        "toys": toys,
    }


def fallback_catalog() -> dict[str, Any]:
    return normalize_catalog(
        {"kinks": _FALLBACK_KINKS, "toys": _FALLBACK_TOYS},
        source="fallback",
    )


async def load_wearer_catalog(
    *,
    chaster: Any,
    memory: Any,
    scene: Any,
    username_hint: str = "",
) -> dict[str, Any]:
    """Build the Domme kit catalog from Chaster, with a starter fallback."""
    snap = scene.snapshot() if scene is not None else {}
    username = (username_hint or "").strip() or (
        (getattr(memory, "sub_name", None) or "").strip()
    )
    catalog = fallback_catalog()
    client = chaster
    if client is not None and getattr(client, "configured", False):
        try:
            st = await client.status()
            username = (st.get("sub_username") or "").strip() or username
            if username:
                profile = await client.get_user_kink_profile(username)
                catalog = normalize_catalog(
                    profile, username=username, source="chaster"
                )
        except Exception as exc:  # noqa: BLE001
            catalog = fallback_catalog()
            catalog["error"] = str(exc)
    catalog["username"] = username or catalog.get("username") or ""
    catalog["selected_kinks"] = list(snap.get("session_kinks") or [])
    catalog["selected_toys"] = list(snap.get("session_toys") or [])
    return catalog


_KIT_CHOICE = re.compile(
    r"\b("
    r"wh?ich (?:of )?(?:his )?(?:toys?|kinks?|fetishes).{0,48}"
    r"(?:use|tonight|today|against|choose|pick)|"
    r"wh?ich should we use|"
    r"(?:choose|pick) (?:one|a toy|a kink)|"
    r"use against him|"
    r"use on him today|"
    r"incorporate"
    r")\b",
    re.I,
)


def wants_kit_choice(message: str) -> bool:
    """True when she wants a named toy/kink pick, not a catalog dump."""
    return bool(_KIT_CHOICE.search(message or ""))


def asked_kit_focus(message: str) -> str:
    text = (message or "").lower()
    wants_toys = bool(re.search(r"\btoys?\b", text))
    wants_kinks = bool(re.search(r"\b(kinks?|fetishes)\b", text))
    if wants_toys and not wants_kinks:
        return "toys"
    if wants_kinks and not wants_toys:
        return "kinks"
    return "both"


def kit_lists_for_choice(
    *,
    session_kinks: list[Any] | None = None,
    session_toys: list[Any] | None = None,
    memory_kinks: list[Any] | None = None,
    catalog: dict[str, Any] | None = None,
) -> tuple[list[str], list[str], str]:
    """Prefer her ticked kit, then his real Chaster profile, then memory."""
    kinks = clean_names(session_kinks)
    toys = clean_names(session_toys)
    source = "kit" if (kinks or toys) else ""
    cat = catalog if isinstance(catalog, dict) else {}
    real = str(cat.get("source") or "") in {"chaster", "mixed"}
    if not kinks and real:
        ranked: list[str] = []
        for want in ("love", "like", "curious", "other"):
            for item in cat.get("kinks") or []:
                if not isinstance(item, dict):
                    continue
                if str(item.get("rating") or "other") == want:
                    ranked.append(str(item.get("name") or ""))
        kinks = clean_names(ranked)
        if kinks:
            source = "profile" if source != "kit" else "kit+profile"
    if not kinks:
        kinks = clean_names(memory_kinks)
        if kinks and not source:
            source = "memory"
    if not toys and real:
        toys = clean_names(
            [
                item.get("name") if isinstance(item, dict) else item
                for item in (cat.get("toys") or [])
            ]
        )
        if toys:
            source = "profile" if source != "kit" else "kit+profile"
    return kinks, toys, source or "none"


def parse_named_kit_pick(
    message: str,
    *,
    kinks: list[str] | None = None,
    toys: list[str] | None = None,
) -> dict[str, str]:
    text = (message or "").lower()
    out: dict[str, str] = {}
    for name in clean_names(kinks):
        if len(name) >= 3 and name.lower() in text:
            out["kink"] = name
            break
    for name in clean_names(toys):
        if len(name) >= 3 and name.lower() in text:
            out["toy"] = name
            break
    return out


def format_kit_choice_block(
    *,
    kinks: list[str] | None,
    toys: list[str] | None,
    focus: str = "both",
    source: str = "",
) -> str:
    kink_list = clean_names(kinks)
    toy_list = clean_names(toys)
    lines = [
        "[KIT CHOICE — she asked you to pick. NAME the item from this list.]",
    ]
    if source:
        lines.append(f"Source: {source}.")
    if focus in {"kinks", "both"}:
        lines.append(
            "Kinks you may name: " + (", ".join(kink_list) if kink_list else "(none on file)")
        )
    if focus in {"toys", "both"}:
        lines.append(
            "Toys you may name: " + (", ".join(toy_list) if toy_list else "(none on file)")
        )
    if not kink_list and not toy_list:
        lines.append(
            "No list loaded. Tell her to open Kinks and tick, or that his "
            "Chaster profile is empty. Do not invent a toy or kink."
        )
    else:
        lines.append(
            "Pick ONE concrete name. Do not say 'the one that makes him squirm' "
            "or 'the one that breaks him'. If she said choose one, decide — "
            "do not ask her which. Tie it to tonight's scene. Stay inside hard limits."
        )
    return "\n".join(lines)


def wants_week_plan(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    return bool(_WEEK_PLAN_RE.search(text) or _HORNY_HINT_RE.search(text))


def build_week_skeleton(
    *,
    kinks: list[str] | None = None,
    toys: list[str] | None = None,
) -> list[dict[str, str]]:
    """Rotate selected kit items across Mon–Sun with a denial beat each day."""
    kink_list = clean_names(kinks)
    toy_list = clean_names(toys)
    if not kink_list:
        kink_list = ["Chastity", "Tease and denial", "Humiliation"]
    if not toy_list:
        toy_list = ["Collar", "Blindfold", "Leather paddle"]

    beats = [
        "Morning ownership ping + cage-check photo. Light tease only — leave him wanting.",
        "Midday ignore, then a sudden explicit instruction. No release.",
        "Edge window (timed). Stop him early. Hide or freeze the timer if he slacks.",
        "Service / ritual day: honorifics, kneeling, a written needy report.",
        "Mean spike: use a selected toy, then go colder than he expects.",
        "Longer scene window. Stack 2 kit items. Denial is the ending, not orgasm.",
        "Aftercare-lite + next-week hook. Remind him the lock stays the point.",
    ]
    days: list[dict[str, str]] = []
    for i, day in enumerate(_WEEKDAYS):
        kink = kink_list[i % len(kink_list)]
        toy = toy_list[i % len(toy_list)]
        extra = toy_list[(i + 1) % len(toy_list)] if i >= 5 else ""
        focus = f"{kink} + {toy}" + (f" + {extra}" if extra and extra != toy else "")
        days.append({"day": day, "focus": focus, "beat": beats[i]})
    return days


def format_session_kit_block(
    *,
    kinks: list[str] | None,
    toys: list[str] | None,
    room: str = "private",
) -> str:
    kink_list = clean_names(kinks)
    toy_list = clean_names(toys)
    if not kink_list and not toy_list:
        return ""
    kink_txt = ", ".join(kink_list) or "(none selected)"
    toy_txt = ", ".join(toy_list) or "(none selected)"
    if room == "private":
        return (
            "\n\n[SESSION KIT — she ticked these to incorporate]\n"
            f"Kinks / fetishes: {kink_txt}\n"
            f"Toys: {toy_txt}\n"
            "Use this kit when proposing scenes, daily tasks, or a weekly plan. "
            "Do not invent toys he does not have. Stay inside hard limits.\n"
            "If she wants a week plan, give a concrete Mon–Sun schedule and "
            "tactics to keep him horny, denied, and submissive. Planning only "
            "until she says execute / go to group.\n"
        )
    return (
        "\n\n[SESSION KIT — incorporate quietly; do not list as a menu to him]\n"
        f"Kinks / fetishes: {kink_txt}\n"
        f"Toys: {toy_txt}\n"
        "Weave selected items into orders and tease. Do not dump the week plan "
        "as a document in group unless the Domme asked you to announce it.\n"
    )


def format_week_plan_private_note(
    *,
    kinks: list[str] | None,
    toys: list[str] | None,
) -> str:
    """Keyholder-only week skeleton — never show this in Group."""
    days = build_week_skeleton(kinks=clean_names(kinks), toys=clean_names(toys))
    lines = "\n".join(f"{d['day']}: {d['focus']} — {d['beat']}" for d in days)
    return (
        "He can see Group, so the week plan stays here.\n\n"
        f"{lines}\n\n"
        "Swap days or make it meaner — say when you want him told a hint, not the plan."
    )


def format_week_planner_block(
    *,
    kinks: list[str] | None,
    toys: list[str] | None,
    room: str = "private",
) -> str:
    kink_list = clean_names(kinks)
    toy_list = clean_names(toys)
    days = build_week_skeleton(kinks=kink_list, toys=toy_list)
    lines = "\n".join(f"  - {d['day']}: {d['focus']} — {d['beat']}" for d in days)
    kit = (
        f"Selected kinks: {', '.join(kink_list) or '(none — pick from his profile loves)'}\n"
        f"Selected toys: {', '.join(toy_list) or '(none — suggest from his real toy list)'}\n"
    )
    where = (
        "Speak TO the human Domme by NAME. This is planning with her, not a group lecture. "
        "Offer the week as something she can approve, swap days, or make meaner. "
        "Do not emit GROUP tags unless she asks to start."
        if room == "private"
        else "She asked in group — give a short owned announcement, not a spreadsheet, "
        "then one concrete order for today from the plan."
    )
    return (
        "\n\n[WEEK PLANNER — help the keyholder design the next 7 days]\n"
        f"{kit}"
        "Suggested skeleton (adapt; do not dump as a sterile table unless she wants that):\n"
        f"{lines}\n"
        "Keep him HORNY:\n"
        "  - Anticipation: name tomorrow's toy or rule the night before.\n"
        "  - Denial rhythm: timed edges, no orgasm; lock stays the point.\n"
        "  - Contrast: sudden warmth, then ignore. Unpredictable check-ins.\n"
        "  - Body: cage-check / kneeling photos; voice or text teases between windows.\n"
        "Keep him SUBMISSIVE:\n"
        "  - Rituals: honorifics, morning report, kneeling, written need.\n"
        "  - Real lock levers when he slacks (add time, freeze, hide timer) — only with facts/tags.\n"
        "  - Service tasks on quieter days so denial is not the only control.\n"
        "  - Weekend longer scene so weekdays stay hungry.\n"
        "Safety: circulation, gag breathing, wax heat, safeword, aftercare still apply.\n"
        f"{where}\n"
    )
