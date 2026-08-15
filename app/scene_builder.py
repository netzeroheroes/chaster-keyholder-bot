"""Build Domme scenes from the Sub's real Chaster kink/toy profile.

Picks suitable toys (matched to loves/likes), uses practice-informed scene
patterns, and sometimes opens with a short mood check first.
"""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# Practice notes distilled from common keyholder / tease&denial guidance
# (anticipation > hardware; blend restraint + denial; check circulation/consent).
_SCENE_PATTERNS: list[dict[str, Any]] = [
    {
        "id": "restraint_denial",
        "needs_any": ["cuff", "spreader", "rope", "collar", "leash", "hood", "sack"],
        "kink_boost": [
            "restraints",
            "sensory deprivation",
            "tease and denial",
            "chastity",
            "power exchange",
        ],
        "beats": [
            "Restrain him so he can't squirm away from the tease.",
            "Keep the cage locked — denial is the point, not release.",
            "Use slow verbal teasing while he's fixed in place.",
            "End with a clear order + when (or if) he may speak.",
        ],
    },
    {
        "id": "gag_control",
        "needs_any": ["gag", "hood", "collar"],
        "kink_boost": ["gag", "humiliation", "power exchange", "slave training"],
        "beats": [
            "Silence him so the cage and your voice do the talking.",
            "Make him nod/answer nonverbally for permission checks.",
            "Pair with posture or leash so he feels owned, not just quiet.",
        ],
    },
    {
        "id": "impact_tease",
        "needs_any": ["paddle", "flogger", "crop", "strap", "wax", "wartenberg"],
        "kink_boost": ["spanking", "wax play", "tease and denial", "humiliation"],
        "beats": [
            "Warm him up lightly — impact as tease, not injury.",
            "Contrast hits with soft denial talk about the locked cage.",
            "Stop while he still wants more; denial lands harder that way.",
        ],
    },
    {
        "id": "humbler_focus",
        "needs_any": ["humbler"],
        "kink_boost": ["chastity", "tease and denial", "restraints", "humiliation"],
        "beats": [
            "Humbler + cage: posture control and helplessness.",
            "Keep sessions timed; watch numbness / circulation.",
            "Tasks while humbled: count strokes of a crop, thank yous, edges denied.",
        ],
    },
    {
        "id": "sensory",
        "needs_any": ["blindfold", "hood", "sensory", "wax", "wartenberg", "wheel"],
        "kink_boost": ["sensory deprivation", "blindfolds", "wax play", "tease and denial"],
        "beats": [
            "Take sight/hearing so every touch on thighs/chest/cage hits harder.",
            "Unpredictable intervals — anticipation is the tease.",
            "Bring him close verbally, then leave him locked and wanting.",
        ],
    },
]

# Soft defaults when profile toys are sparse
_FALLBACK_TOYS = [
    "Blindfold",
    "Collar",
    "Ball gag",
    "Rope",
    "Leather paddle",
]


@dataclass
class BuiltScene:
    toy_count: int
    toys: list[str]
    kink_hooks: list[str]
    pattern_id: str
    beats: list[str]
    mood_check_first: bool
    brief: str
    refs: list[str] = field(default_factory=list)


def wants_scene_build(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    return bool(
        re.search(
            r"\b("
            r"create\s+a\s+(?:scene|session)|build\s+a\s+(?:scene|session)|"
            r"write\s+a\s+(?:scene|session)(?:\s+guide)?|plan\s+a\s+(?:scene|session)|"
            r"session\s+guide|scene\s+guide|scene\s+with|"
            r"pick\s+\d+\s+(?:of\s+)?(?:his\s+)?toys|"
            r"(?:use|choose|select)\s+\d+\s+toys|"
            r"toy\s+scene|scene\s+(?:using|from)\s+(?:his\s+)?toys"
            r")\b",
            text,
            re.I,
        )
    )


def requested_toy_count(message: str, default: int = 3) -> int:
    m = re.search(r"\b(\d+)\s+(?:of\s+)?(?:his\s+)?toys?\b", message or "", re.I)
    if m:
        return max(1, min(6, int(m.group(1))))
    m2 = re.search(r"\bpick\s+(\d+)\b", message or "", re.I)
    if m2:
        return max(1, min(6, int(m2.group(1))))
    return default


def _names(items: list) -> list[str]:
    out: list[str] = []
    for i in items:
        if isinstance(i, dict):
            n = str(i.get("name") or "").strip()
        elif isinstance(i, str):
            n = i.strip()
        else:
            continue
        if n:
            out.append(n)
    return out


def _rating_names(kinks: list, rating: str) -> list[str]:
    want = rating.lower()
    out: list[str] = []
    for k in kinks:
        if not isinstance(k, dict):
            continue
        if str(k.get("rating") or "").lower() == want and k.get("name"):
            out.append(str(k.get("name") or "").strip())
    return out


def _toy_matches(toy: str, needles: list[str]) -> bool:
    low = toy.lower()
    return any(n in low for n in needles)


def pick_toys(
    profile: dict[str, Any],
    *,
    count: int = 3,
    prefer_toys: list[str] | None = None,
    prefer_kinks: list[str] | None = None,
) -> tuple[list[str], list[str], str, list[str]]:
    """Return (toys, kink_hooks, pattern_id, beats)."""
    kinks = list(profile.get("kinks") or [])
    toys = _names(list(profile.get("toys") or []))
    preferred = _names(list(prefer_toys or []))
    if preferred:
        # Domme-selected kit first; keep profile names when they match.
        preferred_present = [
            t for t in toys if any(t.lower() == p.lower() for p in preferred)
        ]
        toys = preferred_present or preferred
    love = [n.lower() for n in _rating_names(kinks, "love")]
    like = [n.lower() for n in _rating_names(kinks, "like")]
    curious = [n.lower() for n in _rating_names(kinks, "curious")]
    pool = love + like

    # Score patterns by kink overlap + available toys
    scored: list[tuple[float, dict[str, Any], list[str]]] = []
    for pat in _SCENE_PATTERNS:
        needs = pat["needs_any"]
        available = [t for t in toys if _toy_matches(t, needs)]
        if not available and toys:
            continue
        boost = 0.0
        for kb in pat["kink_boost"]:
            if any(kb in k for k in pool):
                boost += 2.0
            elif any(kb in k for k in curious):
                boost += 0.8
        boost += min(3.0, len(available) * 0.7)
        scored.append((boost + random.random() * 0.4, pat, available))

    scored.sort(key=lambda x: x[0], reverse=True)
    if scored and scored[0][2]:
        pattern, available = scored[0][1], scored[0][2]
    else:
        pattern = _SCENE_PATTERNS[0]
        available = toys[:] or list(_FALLBACK_TOYS)

    # Prefer toys that match pattern, then fill from remaining profile toys
    chosen: list[str] = []
    random.shuffle(available)
    for t in available:
        if t not in chosen:
            chosen.append(t)
        if len(chosen) >= count:
            break
    if len(chosen) < count:
        rest = [t for t in toys if t not in chosen]
        random.shuffle(rest)
        for t in rest:
            chosen.append(t)
            if len(chosen) >= count:
                break
    if len(chosen) < count and not preferred:
        for t in _FALLBACK_TOYS:
            if t not in chosen:
                chosen.append(t)
            if len(chosen) >= count:
                break

    hooks: list[str] = []
    for name in _names(list(prefer_kinks or [])):
        if name not in hooks:
            hooks.append(name)
    for kb in pattern["kink_boost"]:
        for src in (_rating_names(kinks, "love"), _rating_names(kinks, "like")):
            for name in src:
                if kb in name.lower() and name not in hooks:
                    hooks.append(name)
    hooks = hooks[:6] or _rating_names(kinks, "love")[:4] or ["Chastity", "Tease and denial"]

    return chosen[:count], hooks, str(pattern["id"]), list(pattern["beats"])


def should_mood_check(message: str, *, force: bool | None = None) -> bool:
    """Sometimes open by gauging mood — not every time."""
    if force is not None:
        return force
    text = (message or "").lower()
    if re.search(r"\b(mood|how is he|check in|how'?s he feeling)\b", text):
        return True
    if re.search(r"\b(no mood|skip mood|straight into|just (build|create))\b", text):
        return False
    # ~30% of scene builds start with a short mood probe
    return random.random() < 0.30


async def enrich_refs_from_web(toys: list[str], kink_hooks: list[str]) -> list[str]:
    """Optional short web-informed notes; fails soft if offline."""
    try:
        import httpx
    except ImportError:
        return []
    q = " ".join((toys[:2] + kink_hooks[:2]))[:80]
    if not q.strip():
        return []
    # Use DuckDuckGo lite HTML for a couple of practical snippets (no API key)
    url = "https://duckduckgo.com/html/"
    refs: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            r = await client.get(
                url,
                params={
                    "q": f"{q} chastity cage tease denial keyholder no stroking"
                },
                headers={"User-Agent": "chatbot-scene-builder/1.0"},
            )
            if r.status_code != 200:
                return []
            # Pull a few result titles from HTML
            titles = re.findall(
                r'class="result__a"[^>]*>(.*?)</a>',
                r.text,
                flags=re.I | re.S,
            )
            for t in titles[:3]:
                clean = re.sub(r"<[^>]+>", "", t)
                clean = re.sub(r"\s+", " ", clean).strip()
                if clean and len(clean) > 12:
                    refs.append(clean[:160])
    except Exception:  # noqa: BLE001
        log.debug("Web enrich skipped", exc_info=True)
        return []
    return refs


def format_scene_director_block(scene: BuiltScene, *, room: str) -> str:
    toys = ", ".join(scene.toys)
    hooks = ", ".join(scene.kink_hooks)
    beats = "\n".join(f"  - {b}" for b in scene.beats)
    refs = ""
    if scene.refs:
        refs = "\nWeb-inspired angles:\n" + "\n".join(f"  - {r}" for r in scene.refs)

    mood = ""
    if scene.mood_check_first:
        mood = (
            "\nMOOD CHECK FIRST (this turn only): Ask BOY 1 short in-character question "
            "about how needy/sore/obedient he feels RIGHT NOW. Do not dump the full scene yet — "
            "tease that toys are chosen. Next turn, after he answers, run the scene.\n"
        )
    else:
        mood = (
            "\nNO mood check this time — dive straight into the scene with the picked toys.\n"
        )

    where = (
        "Speak to the human Domme by her NAME with the plan, then if she wants it live "
        "use GROUP tags / be ready to execute."
        if room == "private"
        else "Execute in GROUP: acknowledge the Domme by NAME, then run the scene on BOY now."
    )

    return (
        f"\n\n[SCENE BUILDER — use ONLY these real profile picks]\n"
        f"Toys picked ({scene.toy_count}): {toys}\n"
        f"Kink hooks from his profile: {hooks}\n"
        f"Pattern: {scene.pattern_id}\n"
        f"Beats to weave in:\n{beats}\n"
        f"{refs}\n"
        f"{mood}"
        f"{where}\n"
        "HARD RULES:\n"
        f"- You MUST use each picked toy by name: {toys}.\n"
        "- Do not invent toys he doesn't have.\n"
        "- Keep chastity/denial central; stay inside hard limits.\n"
        "- Give concrete steps (setup → tease → denial beat → closing order).\n"
        "- Safety: circulation, gag breathing, wax heat, safeword still apply.\n"
    )


async def build_scene_from_profile(
    profile: dict[str, Any],
    *,
    message: str,
    room: str = "private",
    web_enrich: bool = True,
    prefer_toys: list[str] | None = None,
    prefer_kinks: list[str] | None = None,
) -> BuiltScene:
    count = requested_toy_count(message, default=3)
    toys, hooks, pattern_id, beats = pick_toys(
        profile,
        count=count,
        prefer_toys=prefer_toys,
        prefer_kinks=prefer_kinks,
    )
    mood = should_mood_check(message)
    refs: list[str] = []
    if web_enrich:
        refs = await enrich_refs_from_web(toys, hooks)

    scene = BuiltScene(
        toy_count=count,
        toys=toys,
        kink_hooks=hooks,
        pattern_id=pattern_id,
        beats=beats,
        mood_check_first=mood,
        brief="",
        refs=refs,
    )
    scene.brief = format_scene_director_block(scene, room=room)
    return scene
