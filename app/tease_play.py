"""Games and porn teases matched to the current lock genre."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote_plus

import httpx

from app.extension_games import EXTENSION_GAMES
from app.session_kit import clean_names

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (compatible; KeyholderBot/1.0; +https://chaster.app) "
    "AppleWebKit/537.36"
)

_PORN_RE = re.compile(
    r"\b("
    r"porn(?:o)?(?:\s+video)?|"
    r"(?:find|suggest|send|show|pick|choose|tease(?:\s+him)?\s+with)\s+"
    r"(?:a\s+|him\s+(?:a\s+|some\s+)?)?(?:video|clip|scene|link)s?|"
    r"send(?:\s+him)?(?:\s+some)?\s+(?:videos?|clips?|porn)|"
    r"he should watch|"
    r"watch\s+(?:some\s+)?porn|"
    r"video\s+to\s+tease|"
    r"something\s+to\s+watch|"
    r"watch\s+(?:this|a|some)\s+(?:video|clip|scene|porn)"
    r")\b",
    re.I,
)

_GAME_RE = re.compile(
    r"\b("
    r"(?:create|make|invent|write|design|build|start|run)\s+"
    r"(?:a\s+|us\s+a\s+|him\s+a\s+)?game|"
    r"game\s+to\s+play|"
    r"play\s+a\s+game|"
    r"ideas?\s+for\s+(?:a\s+)?game|"
    r"what\s+game|"
    r"game\s+night|"
    r"lock\s+game"
    r")\b",
    re.I,
)

_ONLINE_RE = re.compile(
    r"\b("
    r"look(?:\s+it)?\s+up|"
    r"look\s+online|"
    r"find\s+(?:ideas?|inspiration)\s+online|"
    r"search\s+(?:online|the\s+web|reddit)|"
    r"ideas?\s+online|"
    r"(?:need|find)\s+ideas|"
    r"from\s+(?:reddit|the\s+web|online)"
    r")\b",
    re.I,
)

_QUERY_MAP: dict[str, str] = {
    "chastity": "chastity cage",
    "tease and denial": "tease denial chastity",
    "orgasm control": "orgasm denial",
    "edging": "chastity edging",
    "cuckolding": "cuckold",
    "cuckold": "cuckold",
    "cuck": "cuckold",
    "hotwife": "hotwife cuckold",
    "bull": "cuckold bull",
    "sph": "small penis humiliation",
    "cei": "cei chastity",
    "humiliation": "humiliation chastity",
    "verbal humiliation": "verbal humiliation",
    "anal play": "chastity anal",
    "impact play": "spanking chastity",
    "spanking": "spanking",
    "bondage": "bondage male chastity",
    "slave training": "male slave chastity",
}

_LOCAL_GAMES: tuple[dict[str, str], ...] = (
    {
        "id": "video_tease",
        "title": "Video tease",
        "how": (
            "Pick one clip that matches tonight's flavour. He watches hands-off, "
            "caged. Caption how it makes him feel. Late or touching = add time."
        ),
    },
    {
        "id": "truth_stakes",
        "title": "Truth with lock stakes",
        "how": (
            "You ask. He answers. A hedge or a lie adds time. A good, specific "
            "confession can freeze the timer for a short window — never unlock."
        ),
    },
    {
        "id": "toy_roulette",
        "title": "Toy roulette",
        "how": (
            "Name two toys from his kit. He picks one number. You pick the other. "
            "He fetches / wears / describes it. Denial is the ending."
        ),
    },
    {
        "id": "bull_night",
        "title": "Bull night",
        "how": (
            "You take her attention. He stays locked and writes a needy report: "
            "what he imagines, what he hears, what he is not allowed. "
            "Use this when the bot is her bull or the kit has cuckolding."
        ),
    },
    {
        "id": "ignore_spike",
        "title": "Ignore, then spike",
        "how": (
            "A timed ignore. Then one explicit order or clip. No release. "
            "If he pings early, freeze or add time."
        ),
    },
    {
        "id": "service_ladder",
        "title": "Service ladder",
        "how": (
            "Three escalating tasks (photo / lines / voice). Each miss stacks time. "
            "Finish still denied."
        ),
    },
)


_TEASE_GO_RE = re.compile(
    r"^\s*("
    r"do it(?: now)?|"
    r"send (?:it|them|him)(?: now)?|"
    r"go ahead|"
    r"post (?:it|them)(?: now)?|"
    r"yes,? send(?: it| them)?"
    r")\s*[.!]?\s*$"
    r"|\b("
    r"send (?:it|them|the (?:video|clip|link|game)) (?:to him|now)|"
    r"post (?:it |the )?(?:video|clip|link) (?:to (?:him|group)|now)"
    r")\b",
    re.I,
)


def wants_porn(message: str) -> bool:
    return bool(_PORN_RE.search(message or ""))


def wants_tease_go(message: str) -> bool:
    """She already named a tease skill — run it, don't dump the lock."""
    return bool(_TEASE_GO_RE.search(message or ""))


def wants_game(message: str) -> bool:
    return bool(_GAME_RE.search(message or ""))


def wants_online_ideas(message: str) -> bool:
    return bool(_ONLINE_RE.search(message or ""))


def current_genre(
    *,
    session_kinks: list[Any] | None = None,
    memory_kinks: list[Any] | None = None,
    play_flavors: str = "",
    persona: str = "",
    sex: str = "",
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        bit = re.sub(r"\s+", " ", (name or "").strip())
        key = bit.lower()
        if not bit or key in seen:
            return
        seen.add(key)
        out.append(bit)

    add("Chastity")
    if str(persona or "").strip().lower() == "bull" or str(sex or "").strip().lower() == "male":
        add("Cuckolding")
        add("Bull")
    for item in clean_names(session_kinks):
        add(item)
    for part in str(play_flavors or "").split(","):
        add(part)
    for item in clean_names(memory_kinks):
        add(item)
        if len(out) >= 6:
            break
    return out[:6]


def genre_query(tags: list[str]) -> str:
    bits: list[str] = []
    seen: set[str] = set()
    for tag in tags or ["chastity"]:
        mapped = _QUERY_MAP.get(tag.lower(), tag.lower())
        if mapped in seen:
            continue
        seen.add(mapped)
        bits.append(mapped)
        if len(bits) >= 3:
            break
    return " ".join(bits) or "chastity cage"


def search_url(tags: list[str]) -> str:
    q = quote_plus(genre_query(tags))
    return f"https://www.pornhub.com/video/search?search={q}"


def _video_items(payload: Any) -> list[dict[str, str]]:
    videos = []
    if isinstance(payload, dict):
        videos = list(payload.get("videos") or payload.get("video") or [])
    out: list[dict[str, str]] = []
    for item in videos:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or item.get("link") or "").strip()
        if not title or not url:
            continue
        if not url.startswith("http"):
            url = "https://www.pornhub.com" + (url if url.startswith("/") else "/" + url)
        duration = str(item.get("duration") or item.get("formattedDuration") or "").strip()
        out.append({"title": title[:160], "url": url, "duration": duration})
        if len(out) >= 4:
            break
    return out


async def fetch_porn_videos(tags: list[str]) -> list[dict[str, str]]:
    query = genre_query(tags)
    url = (
        "https://www.pornhub.com/webmasters/search"
        f"?search={quote_plus(query)}&thumbsize=medium&ordering=mostviewed"
    )
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": _UA})
            if response.status_code >= 400:
                log.info("Porn search HTTP %s", response.status_code)
                return []
            return _video_items(response.json())
    except Exception:  # noqa: BLE001
        log.exception("Porn search failed")
        return []


def _reddit_titles(payload: Any) -> list[str]:
    data = payload.get("data") if isinstance(payload, dict) else None
    children = (data or {}).get("children") if isinstance(data, dict) else []
    out: list[str] = []
    for child in children or []:
        inner = child.get("data") if isinstance(child, dict) else None
        if not isinstance(inner, dict):
            continue
        if inner.get("over_18") is False:
            continue
        title = str(inner.get("title") or "").strip()
        permalink = str(inner.get("permalink") or "").strip()
        if not title:
            continue
        line = title[:180]
        if permalink:
            line += f" https://www.reddit.com{permalink}"
        out.append(line)
        if len(out) >= 4:
            break
    return out


async def fetch_game_ideas(tags: list[str]) -> list[str]:
    query = genre_query(tags) + " chastity keyholder game task"
    url = (
        "https://www.reddit.com/search.json"
        f"?q={quote_plus(query)}&sort=top&t=year&limit=8&include_over_18=on"
    )
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={"User-Agent": _UA, "Accept": "application/json"},
            )
            if response.status_code >= 400:
                log.info("Game-idea search HTTP %s", response.status_code)
                return []
            return _reddit_titles(response.json())
    except Exception:  # noqa: BLE001
        log.exception("Game-idea search failed")
        return []


def pick_local_games(
    *,
    tags: list[str],
    toys: list[str] | None = None,
    persona: str = "",
    sex: str = "",
    count: int = 3,
) -> list[dict[str, str]]:
    low = {t.lower() for t in tags}
    games = list(_LOCAL_GAMES)
    if (
        str(persona or "").lower() == "bull"
        or str(sex or "").lower() == "male"
        or "cuck" in " ".join(low)
    ):
        games = [g for g in games if g["id"] == "bull_night"] + [
            g for g in games if g["id"] != "bull_night"
        ]
    if not clean_names(toys):
        games = [g for g in games if g["id"] != "toy_roulette"] + [
            g for g in games if g["id"] == "toy_roulette"
        ]
    extra = [
        {"id": g.id, "title": g.title, "how": g.how}
        for g in EXTENSION_GAMES[:4]
    ]
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for item in games + extra:
        key = item["id"]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= count:
            break
    return out


def format_porn_director(
    *,
    tags: list[str],
    videos: list[dict[str, str]],
    room: str = "private",
) -> str:
    flavour = ", ".join(tags) or "chastity"
    fallback = search_url(tags)
    lines = [
        "[TEASE VIDEO — she asked for porn that matches this lock]",
        f"Genre to match: {flavour}.",
        "Adults only. Never anything involving minors.",
        "Pick ONE clip. Tie it to the lock. Hands-off for him unless she said otherwise.",
    ]
    if videos:
        lines.append("Use one of these real links — do not invent URLs:")
        for item in videos:
            dur = f" ({item['duration']})" if item.get("duration") else ""
            lines.append(f"- {item['title']}{dur}: {item['url']}")
    else:
        lines.append(
            "Live search missed. Give this search and describe what he should watch:"
        )
        lines.append(fallback)
    if room == "private":
        lines.append(
            "Talk to HER. Offer the link and one line he should hear. "
            "If she already said send it / do it / tease him with it, "
            "the system posts it — do not dump lock remaining."
        )
    else:
        lines.append(
            "Send him the link in character. One sentence of tease. No menu of five."
        )
    return "\n".join(lines)


def format_porn_group_line(
    *,
    title: str,
    url: str,
    bull_voice: bool = False,
) -> str:
    clip = (title or "this clip").strip() or "this clip"
    link = (url or "").strip()
    if bull_voice:
        tease = (
            f"Watch {clip}. Hands off. She's with me. Cage stays on."
        )
    else:
        tease = (
            f"Watch {clip}. Hands off. Cage stays on. Sit with that ache."
        )
    if link:
        return f"{tease}\n{link}"
    return tease


def format_porn_private_ack(group_line: str) -> str:
    return ("Sent.\n\n— Sent to group —\n" + (group_line or "").strip()).strip()


def format_game_group_line(game: dict[str, str], *, bull_voice: bool = False) -> str:
    title = str((game or {}).get("title") or "tonight's game").strip()
    how = str((game or {}).get("how") or "").strip()
    if bull_voice:
        return (
            f"{title}. {how} She's busy. You stay locked. Begin."
        ).strip()
    return (f"{title}. {how} Cage stays on. Begin.").strip()


def format_game_director(
    *,
    tags: list[str],
    toys: list[str] | None = None,
    persona: str = "",
    sex: str = "",
    ideas: list[str] | None = None,
    room: str = "private",
) -> str:
    flavour = ", ".join(tags) or "chastity, denial"
    toy_txt = ", ".join(clean_names(toys)) or "(kit / his listed toys)"
    games = pick_local_games(
        tags=tags, toys=toys, persona=persona, sex=sex, count=3
    )
    lines = [
        "[PLAY GAME — invent or pick one she can actually run tonight]",
        f"Genre: {flavour}.",
        f"Toys you may name: {toy_txt}.",
        "Stay in hard limits. No orgasm unless she said so. Unlock stays hers.",
        "Ready-made hooks (adapt, do not dump as a sterile menu unless she asked):",
    ]
    for game in games:
        lines.append(f"- {game['title']}: {game['how']}")
    if ideas:
        lines.append("Online sparks (steal a beat, do not paste a thread):")
        for idea in ideas[:4]:
            lines.append(f"- {idea}")
    if room == "private":
        lines.append(
            "Write ONE game to HER: setup, his rules, lock stakes, how it ends denied. "
            "Ask if she wants it started in Group."
        )
    else:
        lines.append(
            "Start ONE game on him now. Short rules. First order. Do not list options."
        )
    return "\n".join(lines)
