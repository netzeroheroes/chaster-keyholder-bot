"""Standalone OpenRouter scene planner. No Chaster, no Cursor login."""

from __future__ import annotations

import json
import logging
import os
import random
import re
from pathlib import Path
from typing import Any

from openai import APIStatusError, AsyncOpenAI

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
INSTRUCTIONS = (ROOT / "instructions.md").read_text(encoding="utf-8")
OPENER = (
    "Kit is saved. Ask for a session of any length — 30 minutes is only an example — "
    "then answer the two questions and I will write the itinerary from your toys, "
    "kinks, and hard limits."
)

MIN_MINUTES = 15
MAX_MINUTES = 480
MAX_TEXT = 800
DEFAULT_MINUTES = 30

FOCUS_PRESETS = (
    "ownership",
    "humiliation",
    "impact",
    "denial",
    "service",
    "objectification",
    "cuckold",
    "training",
    "surprise",
)

INTENSITIES = ("tease", "firm", "cruel", "extreme")
SETTINGS = ("in_person", "distance", "mixed")
ORGASM_POLICIES = ("denied", "ruined", "maybe", "released")
TONES = ("cruel", "teasing", "ritual", "training", "interrogation", "ownership")

KINK_PRESETS = (
    "chastity",
    "orgasm denial",
    "humiliation",
    "verbal degradation",
    "impact",
    "bondage",
    "predicament bondage",
    "CBT",
    "anal training",
    "pegging",
    "gagging",
    "sensory deprivation",
    "objectification",
    "service",
    "worship",
    "pet play",
    "sissification",
    "SPH",
    "cuckold fantasy",
    "CNC (consensual roleplay)",
    "breath control (safety-limited)",
    "wax",
    "electro",
    "collar and leash",
    "edge and deny",
)

_BANNED = re.compile(
    r"\b(child|children|minor|underage|teen(?:ager)?s?|loli|shota|jailbait)\b",
    re.I,
)

_BEATS: list[dict[str, Any]] = [
    {
        "id": "collar_ritual",
        "kinks": {"collar and leash", "ownership", "ritual", "worship"},
        "phase": "Setup",
        "title": "Collar and claim",
        "in_person": (
            "Kneel him, strip him, lock the cage if it isn't already. Collar him "
            "yourself. Have him kiss the inside of the collar and thank you for owning him."
        ),
        "distance": (
            "Order a full-body photo, cage in frame. He puts the collar on on camera "
            "and repeats: 'This neck is yours.'"
        ),
        "sub": "Stay kneeling, eyes down, until given permission to look.",
    },
    {
        "id": "inspection",
        "kinks": {"humiliation", "objectification", "SPH", "service"},
        "phase": "Setup",
        "title": "Livestock inspection",
        "in_person": (
            "Walk around him. Rate his body out loud. Spread him, check the cage, "
            "comment on how little he has to offer."
        ),
        "distance": (
            "Demand poses: face down, ass up, cage close-up, mouth open. Score each photo."
        ),
        "sub": "Hold each pose until she is finished looking.",
    },
    {
        "id": "warmup_impact",
        "kinks": {"impact", "spanking"},
        "phase": "Warm-up",
        "title": "Warm the meat",
        "in_person": (
            "Over the knee or bent over the bed. Hand, then paddle. Count is his job. "
            "A missed count restarts the set. Stop at pink, not broken skin."
        ),
        "distance": (
            "He fetches the paddle and spanks himself on camera to a count you set."
        ),
        "sub": "Count, thank, keep position.",
    },
    {
        "id": "edge_deny",
        "kinks": {"orgasm denial", "edge and deny", "chastity", "tease"},
        "phase": "Core",
        "title": "Edges that go nowhere",
        "in_person": (
            "Vibe or hand over the cage / perineum. Take him to the edge, then stop. "
            "Repeat until he is stupid with it. Cage stays locked."
        ),
        "distance": (
            "Timer edges: 90 seconds of approved stimulation, 60 seconds of nothing. "
            "He must say 'edge' before he tips."
        ),
        "sub": "Ask to edge. Never take it.",
    },
    {
        "id": "cbt",
        "kinks": {"CBT", "cruel", "chastity"},
        "phase": "Core",
        "title": "Caged and tapped",
        "in_person": (
            "Light taps, squeezes, a ruler on the cage. Watch colour. Stop at yellow."
        ),
        "distance": (
            "He taps the cage with a spoon to your count, then ice for 20 seconds."
        ),
        "sub": "Breathe, stay still, safeword if numbness or sharp pain.",
    },
    {
        "id": "predicament",
        "kinks": {"predicament bondage", "bondage", "objectification"},
        "phase": "Peak",
        "title": "Choose the hurt",
        "in_person": (
            "Tie him so standing eases the gag but strains the cage, or kneeling eases "
            "the cage but chokes the gag. He picks. You wait and watch."
        ),
        "distance": (
            "Wall sit with a clothespin on each nipple, cage visible. If his thighs "
            "drop, he adds two minutes and a written apology."
        ),
        "sub": "Hold. If he must switch, he asks.",
    },
    {
        "id": "gag_silence",
        "kinks": {"gagging", "humiliation", "objectification"},
        "phase": "Core",
        "title": "Shut him up",
        "in_person": (
            "Gag him. He answers yes/no with nods. Use him as furniture for a few minutes."
        ),
        "distance": (
            "A gag in his mouth on camera. He may only type. Spoken words cost extra edges."
        ),
        "sub": "Breathe around the gag. Tap twice for yellow.",
    },
    {
        "id": "anal",
        "kinks": {"anal training", "pegging", "objectification"},
        "phase": "Core",
        "title": "Open him",
        "in_person": (
            "Lube, slow plug or fingers, then the toy he earned. Pace is yours. "
            "Cage stays on."
        ),
        "distance": (
            "He lubes and sits on a plug for a timed hold, camera behind. You tell him when he may stand."
        ),
        "sub": "Relax, receive, do not ask to cum.",
    },
    {
        "id": "service",
        "kinks": {"service", "worship", "ownership"},
        "phase": "Core",
        "title": "Useful for once",
        "in_person": (
            "Body worship: feet, boots, thighs. Then a real task — water, tidy, present the next toy."
        ),
        "distance": (
            "Written lines plus a chore with proof photo. Then 5 minutes of spoken worship."
        ),
        "sub": "Do it properly. Rushing is disrespect.",
    },
    {
        "id": "degrade",
        "kinks": {"verbal degradation", "humiliation", "SPH", "sissification"},
        "phase": "Core",
        "title": "Name him correctly",
        "in_person": (
            "A mantra he repeats while you ignore him, then a new name for the night."
        ),
        "distance": (
            "He records a 30-second clip using the name you give him, then sends lines until the grammar is perfect."
        ),
        "sub": "Use the name. Correct himself if he slips.",
    },
    {
        "id": "cnc_hold",
        "kinks": {"CNC (consensual roleplay)", "bondage", "ownership"},
        "phase": "Peak",
        "title": "Held and used (negotiated)",
        "in_person": (
            "Remind him this is the scene he asked for. Pin or cuff him. Take what "
            "you want within limits. Check yellow twice."
        ),
        "distance": (
            "Scripted resistance: he must follow orders he 'doesn't want'. Safeword is real."
        ),
        "sub": "Safeword is real. Play-struggle is not a safeword.",
    },
    {
        "id": "pet",
        "kinks": {"pet play", "collar and leash", "objectification"},
        "phase": "Core",
        "title": "On the floor",
        "in_person": (
            "No furniture. He crawls, waits at your heel, drinks from a bowl if that is in limits."
        ),
        "distance": (
            "Floor only. Collar on. He may not sit on chairs. Proof photos every ten minutes."
        ),
        "sub": "Stay down. Human speech costs a swat.",
    },
    {
        "id": "sensory",
        "kinks": {"sensory deprivation", "wax", "electro", "bondage"},
        "phase": "Core",
        "title": "Take his senses",
        "in_person": (
            "Blindfold, optional earplugs. Unpredictable touch — ice, nails, wax if listed."
        ),
        "distance": (
            "Blindfold on camera. You send audio cues. Peeking adds ten minutes of denial."
        ),
        "sub": "Keep the blindfold. Hands where she put them.",
    },
    {
        "id": "denied_close",
        "kinks": {"orgasm denial", "chastity", "edge and deny"},
        "phase": "Close",
        "title": "Put it away",
        "in_person": (
            "One last almost. Then lock, dress, a kiss on the forehead or a slap. "
            "Tell him when he may next ask."
        ),
        "distance": (
            "Final edge. Cage check photo. He writes when he is allowed to ask again. You do not answer tonight."
        ),
        "sub": "No orgasm. Thank her for the denial.",
    },
]

_AFTERCARE = [
    "Water, blanket, and a real check-in — not in-scene voice.",
    "Look at skin, joints, cage, jaw, and mood. Treat marks.",
    "He may speak in full sentences. Ask what landed and what to cut.",
    "If he dropped hard, stay with him until he is back in his name.",
]


def catalog() -> dict[str, Any]:
    return {
        "opener": OPENER,
        "intensities": list(INTENSITIES),
        "settings": list(SETTINGS),
        "orgasm_policies": list(ORGASM_POLICIES),
        "tones": list(TONES),
        "kinks": list(KINK_PRESETS),
        "focuses": list(FOCUS_PRESETS),
        "duration": {"min": MIN_MINUTES, "max": MAX_MINUTES, "default": DEFAULT_MINUTES},
        "provider": "openrouter",
        "dynamic": "female_dominant_male_submissive",
    }


def surprise_brief() -> dict[str, Any]:
    rng = random.Random()
    return {
        "duration_minutes": rng.choice([45, 60, 75, 90, 120]),
        "intensity": rng.choice(("cruel", "extreme", "extreme")),
        "setting": rng.choice(SETTINGS),
        "tone": rng.choice(TONES),
        "orgasm": rng.choice(("denied", "denied", "ruined")),
        "kinks": rng.sample(list(KINK_PRESETS), k=rng.randint(3, 6)),
        "toys": "",
        "limits": "",
        "notes": "Surprise me. Be demanding.",
        "experience": "experienced",
    }


def _clip(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:MAX_TEXT]


def _string_list(value: Any, *, fallback: list[str]) -> list[str]:
    if isinstance(value, str):
        parts = [p.strip() for p in re.split(r"[,;\n]+", value) if p.strip()]
    elif isinstance(value, list):
        parts = [str(p).strip() for p in value if str(p).strip()]
    else:
        parts = []
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(part[:80])
        if len(out) >= 12:
            break
    return out or list(fallback)


def _limit_terms(limits: str) -> list[str]:
    return [p.strip().lower() for p in re.split(r"[,;\n/]+", limits) if p.strip()]


def respects_limits(text: str, limits: str) -> bool:
    blob = (text or "").lower()
    for term in _limit_terms(limits):
        if len(term) >= 3 and term in blob:
            return False
    return True


def sanitize_brief(raw: dict[str, Any] | None) -> dict[str, Any]:
    src = dict(raw or {})
    duration = max(MIN_MINUTES, min(MAX_MINUTES, int(src.get("duration_minutes") or DEFAULT_MINUTES)))
    intensity = str(src.get("intensity") or "extreme").strip().lower()
    if intensity not in INTENSITIES:
        intensity = "extreme"
    setting = str(src.get("setting") or "in_person").strip().lower()
    if setting not in SETTINGS:
        setting = "in_person"
    tone = str(src.get("tone") or "cruel").strip().lower()
    if tone not in TONES:
        tone = "cruel"
    orgasm = str(src.get("orgasm") or "denied").strip().lower()
    if orgasm not in ORGASM_POLICIES:
        orgasm = "denied"
    kinks = _string_list(src.get("kinks"), fallback=list(KINK_PRESETS[:4]))
    toys = _clip(src.get("toys") or "")
    limits = _clip(src.get("limits") or "")
    notes = _clip(src.get("notes") or "")
    if _BANNED.search(" ".join([toys, limits, notes, " ".join(kinks)])):
        raise ValueError("This planner is adults 18+ only.")
    return {
        "duration_minutes": duration,
        "intensity": intensity,
        "setting": setting,
        "tone": tone,
        "orgasm": orgasm,
        "experience": str(src.get("experience") or "practiced").strip().lower(),
        "kinks": kinks,
        "toys": toys,
        "limits": limits,
        "notes": notes,
    }


def sanitize_kit(raw: dict[str, Any] | None) -> dict[str, Any]:
    src = dict(raw or {})
    kinks = _string_list(src.get("kinks"), fallback=[])
    toys = _clip(src.get("toys") or "")
    limits = _clip(src.get("limits") or "")
    extra = _clip(src.get("extra") or "")
    if _BANNED.search(" ".join([toys, limits, extra, " ".join(kinks)])):
        raise ValueError("This planner is adults 18+ only.")
    return {"toys": toys, "kinks": kinks, "limits": limits, "extra": extra}


def sanitize_session(raw: dict[str, Any] | None) -> dict[str, Any]:
    src = dict(raw or {})
    try:
        minutes = int(src.get("duration_minutes") or DEFAULT_MINUTES)
    except (TypeError, ValueError):
        minutes = DEFAULT_MINUTES
    focus = str(src.get("focus") or "").strip().lower()
    if focus and focus not in FOCUS_PRESETS:
        focus = _clip(src.get("focus") or "")[:80]
    orgasm = str(src.get("orgasm") or "denied").strip().lower()
    if orgasm not in ORGASM_POLICIES:
        orgasm = "denied"
    notes = _clip(src.get("notes") or "")
    if _BANNED.search(" ".join([str(focus), notes])):
        raise ValueError("This planner is adults 18+ only.")
    return {
        "duration_minutes": max(MIN_MINUTES, min(MAX_MINUTES, minutes)),
        "focus": focus or "ownership",
        "orgasm": orgasm,
        "notes": notes,
    }


def kit_block(kit: dict[str, Any], session: dict[str, Any] | None = None) -> str:
    clean = sanitize_kit(kit)
    kinks = ", ".join(clean["kinks"]) or "(none picked)"
    toys = clean["toys"] or "(none listed — household furniture, hands, voice only)"
    limits = clean["limits"] or "none specified — keep default safety"
    lines = [
        "KIT (always honor this):",
        f"Toys: {toys}",
        f"Kinks to lean on: {kinks}",
        f"Hard limits (never include): {limits}",
        "Dynamic: female dominant, male submissive.",
    ]
    if session:
        brief = sanitize_session(session)
        lines += [
            f"Play time: {brief['duration_minutes']} minutes. Timed beats are play only "
            "and must fill this length. Aftercare is after the clock, untimed, not counted.",
            f"Tonight's job: {brief['focus']}",
            f"Orgasm policy: {brief['orgasm']}",
            f"Extra notes: {brief['notes'] or '(none)'}",
        ]
    return "\n".join(lines)


def extract_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _time_slices(duration: int, n: int) -> list[tuple[int, int]]:
    n = max(1, n)
    base = duration / n
    out: list[tuple[int, int]] = []
    cursor = 0.0
    for i in range(n):
        nxt = duration if i == n - 1 else round(cursor + base)
        start = int(round(cursor))
        end = max(start + 1, int(nxt))
        out.append((start, min(duration, end)))
        cursor = end
    if out:
        last_start, _ = out[-1]
        out[-1] = (last_start, duration)
    return out


def compose_itinerary(brief: dict[str, Any]) -> dict[str, Any]:
    duration = int(brief["duration_minutes"])
    setting = brief["setting"]
    kink_set = {k.lower() for k in brief["kinks"]}
    limits = brief["limits"]
    tone = str(brief.get("tone") or "").lower()
    picked: list[dict[str, Any]] = []
    for beat in _BEATS:
        tags = {k.lower() for k in beat["kinks"]}
        if tags & kink_set or tone in tags:
            blob = f"{beat['title']} {beat['in_person']} {beat['distance']}"
            if respects_limits(blob, limits):
                picked.append(beat)
    ids = {b["id"] for b in picked}
    for needed in ("collar_ritual", "denied_close"):
        extra = next((b for b in _BEATS if b["id"] == needed), None)
        if extra and extra["id"] not in ids and respects_limits(extra["title"], limits):
            picked.append(extra)
            ids.add(extra["id"])
    order = {"Setup": 0, "Warm-up": 1, "Core": 2, "Peak": 3, "Close": 4}
    picked.sort(key=lambda b: order.get(str(b["phase"]), 9))
    target = 6 if duration < 50 else 8 if duration < 100 else 10
    while len(picked) < target:
        pool = [
            b
            for b in _BEATS
            if b["id"] not in {p["id"] for p in picked} and respects_limits(b["title"], limits)
        ]
        if not pool:
            break
        picked.append(pool[len(picked) % len(pool)])
    picked = picked[:target] or [b for b in _BEATS if respects_limits(b["title"], limits)][:6]
    slices = _time_slices(duration, len(picked))
    key = "distance" if setting == "distance" else "in_person"
    steps = []
    for beat, (start, end) in zip(picked, slices):
        domme = str(beat[key])
        if brief["orgasm"] == "denied" and beat["id"] != "denied_close":
            domme += " Orgasm is not on the table."
        steps.append(
            {
                "start_min": start,
                "end_min": end,
                "phase": beat["phase"],
                "title": beat["title"],
                "domme": domme,
                "sub": beat["sub"],
                "notes": "Watch colour, breathing, and yellow."
                if beat["phase"] == "Peak"
                else f"Orgasm policy is {brief['orgasm']}.",
            }
        )
    toys = [t.strip() for t in re.split(r"[,;\n]+", brief["toys"]) if t.strip()]
    kinks = ", ".join(brief["kinks"][:4])
    where = {
        "in_person": "You have him in the room.",
        "distance": "You are not in the room — voice, photos, and orders only.",
        "mixed": "Start remote; finish him in person if you can.",
    }[setting]
    return {
        "title": f"{brief['tone'].title()} ruin — {duration} minutes"
        if brief["intensity"] == "extreme"
        else f"{brief['tone'].title()} session — {duration} minutes",
        "premise": (
            f"{where} Intensity is {brief['intensity']}, tone {brief['tone']}. "
            f"Lean on {kinks}. Orgasm policy: {brief['orgasm']}. You run the clock."
        ),
        "intensity": brief["intensity"],
        "duration_minutes": duration,
        "setting": setting,
        "tone": brief["tone"],
        "orgasm": brief["orgasm"],
        "kinks": list(brief["kinks"]),
        "warnings": [
            "Adults 18+ only. Negotiate first. Safeword beats the script.",
            "Stop for numbness, cold extremities, panic, or a red.",
        ],
        "equipment": toys
        or ["collar", "cuffs or rope", "gag", "paddle", "chastity cage", "lube"],
        "safeword": {"green": "green", "yellow": "yellow", "red": "red"},
        "steps": steps,
        "aftercare": list(_AFTERCARE),
        "variations": [
            "Add a second predicament in the last third if he is still coherent.",
            "Swap impact for longer denial if his skin has had enough.",
        ],
        "source": "composed",
    }


def normalize_itinerary(data: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    steps_in = data.get("steps") if isinstance(data.get("steps"), list) else []
    steps: list[dict[str, Any]] = []
    for raw in steps_in:
        if not isinstance(raw, dict):
            continue
        start = int(raw.get("start_min") or 0)
        end = int(raw.get("end_min") or start + 5)
        blob = " ".join(
            str(raw.get(k) or "") for k in ("title", "domme", "sub", "notes", "phase")
        )
        if not respects_limits(blob, brief["limits"]):
            continue
        steps.append(
            {
                "start_min": max(0, start),
                "end_min": min(MAX_MINUTES, max(start + 1, end)),
                "phase": _clip(raw.get("phase") or "Beat")[:40],
                "title": _clip(raw.get("title") or "Beat")[:80],
                "domme": _clip(raw.get("domme") or "")[:1200],
                "sub": _clip(raw.get("sub") or "")[:600],
                "notes": _clip(raw.get("notes") or "")[:400],
            }
        )
    fallback = compose_itinerary(brief)
    if len(steps) < 4:
        return fallback
    safeword = data.get("safeword") if isinstance(data.get("safeword"), dict) else {}
    equipment = data.get("equipment") if isinstance(data.get("equipment"), list) else []
    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    aftercare = data.get("aftercare") if isinstance(data.get("aftercare"), list) else []
    variations = data.get("variations") if isinstance(data.get("variations"), list) else []
    return {
        "title": _clip(data.get("title") or fallback["title"])[:120],
        "premise": _clip(data.get("premise") or fallback["premise"])[:800],
        "intensity": brief["intensity"],
        "duration_minutes": brief["duration_minutes"],
        "setting": brief["setting"],
        "tone": brief["tone"],
        "orgasm": brief["orgasm"],
        "kinks": list(brief["kinks"]),
        "warnings": [_clip(w)[:240] for w in warnings[:8]] or fallback["warnings"],
        "equipment": [_clip(x)[:80] for x in equipment[:16]] or fallback["equipment"],
        "safeword": {
            "green": _clip(safeword.get("green") or "green")[:40],
            "yellow": _clip(safeword.get("yellow") or "yellow")[:40],
            "red": _clip(safeword.get("red") or "red")[:40],
        },
        "steps": steps,
        "aftercare": [_clip(x)[:240] for x in aftercare[:8]] or fallback["aftercare"],
        "variations": [_clip(x)[:240] for x in variations[:6]],
        "source": "openrouter",
    }


def scene_markdown(scene: dict[str, Any]) -> str:
    limits = scene.get("limits") or (
        "None specified. I will assume you have no hard limits, but I will keep "
        "safety in mind (no blood, no permanent damage, no scat/urine unless you "
        "say otherwise)."
    )
    toys = ", ".join(scene.get("equipment") or []) or "household furniture, voice, hands"
    lines = [
        f"**Hard Limits:** {limits}",
        "",
        f'**Theme:** "{scene["title"]}" – {scene["premise"]}',
        "",
        f"**Duration:** {scene.get('duration_minutes', '')} minutes of play "
        "(aftercare is after the clock)",
        "",
        f"**Toys Available:** {toys}.",
        "",
        "**Dynamic:** Female Dominant, Male Submissive.",
        "",
        f"**Scenario: {scene['title']}**",
        "",
    ]
    for i, step in enumerate(scene.get("steps") or [], 1):
        title = step.get("title") or "Beat"
        body = " ".join(
            p for p in (step.get("domme"), step.get("sub"), step.get("notes")) if p
        )
        start = step.get("start_min")
        end = step.get("end_min")
        timing = f" ({start}–{end} min)" if start is not None and end is not None else ""
        lines.append(f"{i}. **{title}{timing}:** {body}")
    lines += ["", "**Aftercare (after the clock, not play time):**"]
    for i, line in enumerate(scene.get("aftercare") or _AFTERCARE, 1):
        lines.append(f"- {line}")
    return "\n".join(lines)


def compose_chat_reply(
    user_text: str,
    kit: dict[str, Any] | None = None,
    session: dict[str, Any] | None = None,
) -> str:
    kit_data = sanitize_kit(kit) if kit else {"toys": "", "kinks": [], "limits": ""}
    sess = sanitize_session(session) if session else sanitize_session({})
    limits_match = re.search(r"limits?\s*[:\-]\s*(.+)$", user_text, re.I | re.S)
    limits = kit_data["limits"] or (limits_match.group(1).strip() if limits_match else "")
    brief = sanitize_brief(
        {
            "duration_minutes": sess["duration_minutes"],
            "toys": kit_data["toys"] or user_text,
            "kinks": kit_data["kinks"] or None,
            "limits": limits,
            "notes": " ".join(p for p in (sess["focus"], sess["notes"], user_text) if p),
            "orgasm": sess["orgasm"],
            "tone": "ownership" if sess["focus"] == "ownership" else "cruel",
        }
    )
    scene = compose_itinerary(brief)
    if limits:
        scene["limits"] = limits
    return scene_markdown(scene)


def _clean_messages(messages: list[dict[str, Any]], *, inject_opener: bool = True) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    blob: list[str] = []
    for raw in messages[-24:]:
        role = str(raw.get("role") or "")
        content = str(raw.get("content") or "").strip()[:8000]
        if role not in {"user", "assistant"} or not content:
            continue
        blob.append(content)
        out.append({"role": role, "content": content})
    if _BANNED.search(" ".join(blob)):
        raise ValueError("This planner is adults 18+ only.")
    if inject_opener and (not out or out[0]["role"] != "assistant"):
        out.insert(0, {"role": "assistant", "content": OPENER})
    return out


def _llm_settings() -> dict[str, str]:
    from dotenv import load_dotenv

    load_dotenv(REPO / ".env")
    load_dotenv(ROOT / ".env")
    return {
        "api_key": (os.getenv("LLM_API_KEY") or "").strip(),
        "base_url": (os.getenv("LLM_BASE_URL") or "https://openrouter.ai/api/v1").strip(),
        "model": (
            os.getenv("LLM_MODEL")
            or "cognitivecomputations/dolphin-mistral-24b-venice-edition"
        ).strip(),
        "app_name": (os.getenv("OPENROUTER_APP_NAME") or "scene-planner").strip(),
        "site_url": (os.getenv("OPENROUTER_SITE_URL") or "http://127.0.0.1:8787").strip(),
    }


def llm_configured() -> bool:
    return bool(_llm_settings()["api_key"])


async def _openrouter_chat(messages: list[dict[str, str]]) -> str:
    cfg = _llm_settings()
    if not cfg["api_key"]:
        return ""
    headers: dict[str, str] = {}
    if "openrouter.ai" in cfg["base_url"]:
        headers["HTTP-Referer"] = cfg["site_url"]
        headers["X-Title"] = cfg["app_name"]
    client = AsyncOpenAI(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        default_headers=headers or None,
    )
    max_tokens = 3500
    try:
        for _ in range(3):
            try:
                completion = await client.chat.completions.create(
                    model=cfg["model"],
                    messages=[{"role": "system", "content": INSTRUCTIONS}, *messages],
                    max_tokens=max_tokens,
                    temperature=0.95,
                )
                break
            except APIStatusError as exc:
                if exc.status_code == 402 and max_tokens > 600:
                    max_tokens = max(600, max_tokens // 2)
                    log.warning("OpenRouter 402 — retry max_tokens=%s", max_tokens)
                    continue
                raise
        else:
            return ""
        choice = (completion.choices or [None])[0]
        if choice is None or choice.message is None:
            return ""
        content = choice.message.content
        if isinstance(content, str):
            return content.strip()
        return str(content or "").strip()
    finally:
        await client.close()


async def chat(
    messages: list[dict[str, Any]],
    kit: dict[str, Any] | None = None,
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kit_data = sanitize_kit(kit) if kit is not None else None
    sess = sanitize_session(session) if session is not None else None
    history = _clean_messages(messages, inject_opener=not kit_data)
    last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    fallback = compose_chat_reply(last_user or "collar, cuffs, paddle", kit_data, sess)
    if kit_data or sess:
        primed = [
            {"role": "user", "content": kit_block(kit_data or {}, sess)},
            {
                "role": "assistant",
                "content": (
                    "Kit received. I will use only those toys, lean on those kinks, "
                    "never cross the hard limits, and fill the asked minutes with play. "
                    "Aftercare comes after the clock."
                ),
            },
        ]
        history = primed + [m for m in history if m["content"] != OPENER]
    if not last_user and not (kit_data and sess):
        return {"reply": OPENER, "source": "opener"}
    if not last_user and kit_data and sess:
        last_user = (
            f"Write a {sess['duration_minutes']} minute session. "
            f"Tonight's job: {sess['focus']}. Orgasm: {sess['orgasm']}."
        )
        history.append({"role": "user", "content": last_user})
    if not llm_configured():
        return {
            "reply": fallback,
            "source": "composed",
            "detail": "LLM_API_KEY missing — used local composer",
        }
    try:
        raw = await _openrouter_chat(history)
    except Exception:  # noqa: BLE001
        log.exception("OpenRouter scene chat failed")
        return {
            "reply": fallback,
            "source": "composed",
            "detail": "OpenRouter failed — used local composer",
        }
    if not raw:
        return {
            "reply": fallback,
            "source": "composed",
            "detail": "Model returned nothing — used local composer",
        }
    return {"reply": raw, "source": "openrouter"}


async def plan_scene(brief: dict[str, Any]) -> dict[str, Any]:
    clean = sanitize_brief(brief)
    fallback = compose_itinerary(clean)
    fallback["markdown"] = scene_markdown(fallback)
    if not llm_configured():
        fallback["detail"] = "LLM_API_KEY missing — used local composer"
        return fallback
    try:
        raw = await _openrouter_chat(
            [
                {"role": "assistant", "content": OPENER},
                {
                    "role": "user",
                    "content": (
                        f"Toys: {clean['toys'] or 'collar, cuffs, paddle, cage'}\n"
                        f"Hard limits: {clean['limits'] or 'none specified'}\n"
                        f"{clean['notes']}"
                    ),
                },
            ]
        )
    except Exception:  # noqa: BLE001
        log.exception("OpenRouter scene plan failed")
        fallback["detail"] = "OpenRouter failed — used local composer"
        return fallback
    if raw:
        return {
            **fallback,
            "markdown": raw,
            "source": "openrouter",
            "title": fallback["title"],
        }
    fallback["detail"] = "Model returned nothing — used local composer"
    return fallback
