"""Games and porn teases matched to the current lock genre."""

from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx

from app.extension_games import EXTENSION_GAMES
from app.session_kit import clean_names

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (compatible; KeyholderBot/1.0; +https://chaster.app) "
    "AppleWebKit/537.36"
)

_MEDIA = r"(?:video|clip|scene|link|pic(?:ture)?|photo|image)s?"
_PORN_RE = re.compile(
    r"\b("
    r"porn(?:o)?(?:\s+video)?|"
    r"(?:find|suggest|send|show|pick|choose|tease(?:\s+him)?\s+with)\s+"
    r"(?:a\s+|him\s+(?:a\s+|some\s+)?)?" + _MEDIA + r"(?:\s+or\s+" + _MEDIA + r")?|"
    r"send(?:\s+him)?(?:\s+(?:a|some|an?))?\s+" + _MEDIA + r"(?:\s+or\s+" + _MEDIA + r")?|"
    r"he should watch|"
    r"watch\s+(?:some\s+)?porn|"
    r"video\s+to\s+tease|"
    r"something\s+to\s+(?:watch|look at)|"
    r"(?:picture|pic|photo|image|video|clip)\s+or\s+(?:video|clip|picture|pic|photo|image)|"
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

# 18+ media-heavy subs only. Skip personals / meetup boards.
_TAG_SUBS: dict[str, tuple[str, ...]] = {
    "chastity": ("MaleChastity", "Chastity", "chastitycages"),
    "cuckolding": ("Cuckold", "hotwife", "cuckoldcaptions"),
    "cuckold": ("Cuckold", "hotwife", "cuckoldcaptions"),
    "cuck": ("Cuckold", "hotwife"),
    "hotwife": ("hotwife", "Cuckold"),
    "bull": ("Cuckold", "hotwife"),
    "sph": ("SPH", "smallpenishumiliation"),
    "cei": ("cumeatinginstruction",),
    "humiliation": ("Femdom", "SPH"),
    "tease and denial": ("OrgasmDenial", "MaleChastity"),
    "orgasm control": ("OrgasmDenial", "MaleChastity"),
    "edging": ("OrgasmDenial", "edging"),
    "anal play": ("pegging", "anal"),
    "pegging": ("pegging",),
    "spanking": ("spanking",),
    "impact play": ("spanking",),
    "bondage": ("Femdom", "MaleChastity"),
}

_DEFAULT_SUBS: tuple[str, ...] = ("MaleChastity", "Cuckold", "cuckoldcaptions")

_UNSAFE_TITLE = re.compile(
    r"\b("
    r"teen(?:ager)?s?|loli|shota|underage|minor|child|kid|"
    r"jailbait|preteen|young\s+girl"
    r")\b",
    re.I,
)

_SEARCH_PAGE = re.compile(
    r"pornhub\.com/video/search|/video/search\?|"
    r"xvideos\.com/\?k=|xhamster\.com/search|"
    r"reddit\.com/search|reddit\.com/r/[^/]+/?(\?|$)",
    re.I,
)

_IMAGE_FILE = re.compile(
    r"\.(gif|gifv|jpe?g|png|webp)(\?|$)",
    re.I,
)

_DIRECT_MEDIA_HOSTS = (
    "i.redd.it",
    "preview.redd.it",
    "i.imgur.com",
    "imgur.com",
    "redgifs.com",
    "gfycat.com",
    "redgif.com",
    "v.redd.it",
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


def subs_for_tags(tags: list[str]) -> list[str]:
    """Pick NSFW media subs that match this lock's flavour."""
    out: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        key = (name or "").strip()
        if not key or key.lower() in seen:
            return
        seen.add(key.lower())
        out.append(key)

    for tag in tags or []:
        mapped = _TAG_SUBS.get(str(tag or "").strip().lower())
        if mapped:
            for sub in mapped:
                add(sub)
        if len(out) >= 4:
            break
    if not out:
        for sub in _DEFAULT_SUBS:
            add(sub)
    # Always keep a chastity board in the mix
    if "malechastity" not in seen and "chastity" not in seen:
        add("MaleChastity")
    return out[:4]


def search_url(tags: list[str]) -> str:
    """A board to browse — never send this as 'the clip'."""
    sub = (subs_for_tags(tags) or ["MaleChastity"])[0]
    return f"https://www.reddit.com/r/{sub}/"


def is_specific_tease_link(url: str) -> bool:
    """True for a clickable clip/pic/post — not a search or sub listing."""
    raw = (url or "").strip()
    if not raw.startswith("http"):
        return False
    if _SEARCH_PAGE.search(raw):
        return False
    low = raw.lower()
    if "/comments/" in low or "/gallery/" in low:
        return True
    host = (urlparse(raw).hostname or "").lower()
    if any(h == host or host.endswith("." + h) for h in _DIRECT_MEDIA_HOSTS):
        return True
    if any(
        bit in low
        for bit in (
            "redgifs.com/watch",
            "pornhub.com/view_video",
            "xvideos.com/video",
            "xnxx.com/video",
            "xhamster.com/videos",
        )
    ):
        return True
    return bool(_IMAGE_FILE.search(low) or re.search(r"\.(mp4|webm)(\?|$)", low))


def tease_kind(url: str) -> str:
    low = (url or "").lower()
    if _IMAGE_FILE.search(low) or "i.redd.it" in low or "i.imgur.com" in low:
        return "image"
    if "/gallery/" in low:
        return "image"
    return "video"


def redgif_iframe(url: str) -> str:
    match = re.search(
        r"redgifs\.com/(?:watch|ifr)/([A-Za-z0-9]+)", url or "", re.I
    )
    if not match:
        return ""
    return f"https://www.redgifs.com/ifr/{match.group(1)}"


def tease_media_fields(
    *,
    url: str = "",
    kind: str = "",
    image_url: str = "",
    video_url: str = "",
    embed_url: str = "",
) -> dict[str, str]:
    """URLs the chat UI can show in-bubble like a messenger."""
    link = (url or "").strip()
    kind = (kind or tease_kind(link)).lower()
    image_url = (image_url or "").strip()
    video_url = (video_url or "").strip()
    embed_url = (embed_url or "").strip() or redgif_iframe(link) or redgif_iframe(
        video_url
    )
    if not image_url and kind == "image" and is_specific_tease_link(link):
        image_url = link
    if not video_url and re.search(r"\.(mp4|webm)(\?|$)", link, re.I):
        video_url = link
    out: dict[str, str] = {}
    if image_url:
        out["image_url"] = image_url
    if video_url:
        out["video_url"] = video_url
    if embed_url:
        out["embed_url"] = embed_url
    if is_specific_tease_link(link):
        out["page_url"] = link
    return out


def _reddit_video_url(data: dict[str, Any]) -> str:
    for key in ("media", "secure_media"):
        block = data.get(key)
        if not isinstance(block, dict):
            continue
        hosted = block.get("reddit_video")
        if not isinstance(hosted, dict):
            continue
        raw = str(hosted.get("fallback_url") or "").strip()
        if raw.startswith("http"):
            return raw.split("?")[0]
    return ""


def _reddit_preview_image(data: dict[str, Any]) -> str:
    preview = data.get("preview") if isinstance(data.get("preview"), dict) else {}
    images = preview.get("images") if isinstance(preview, dict) else []
    if not images or not isinstance(images[0], dict):
        return ""
    source = images[0].get("source") if isinstance(images[0].get("source"), dict) else {}
    raw = str((source or {}).get("url") or "").replace("&amp;", "&").strip()
    return raw if raw.startswith("http") else ""


def _abs_reddit(path: str) -> str:
    bit = (path or "").strip()
    if bit.startswith("http"):
        return bit
    if bit.startswith("/"):
        return "https://www.reddit.com" + bit
    return ""


def _media_url_from_post(data: dict[str, Any]) -> str:
    """Direct picture/gif/redgif when we can; else the Reddit post he can open."""
    if not isinstance(data, dict):
        return ""
    if data.get("stickied") or data.get("removed_by_category"):
        return ""
    if data.get("over_18") is False:
        return ""
    title = str(data.get("title") or "")
    if _UNSAFE_TITLE.search(title):
        return ""
    permalink = _abs_reddit(str(data.get("permalink") or ""))
    dest = str(
        data.get("url_overridden_by_dest") or data.get("url") or ""
    ).strip()
    if dest.startswith("/"):
        dest = _abs_reddit(dest)
    domain = str(data.get("domain") or "").lower()
    hint = str(data.get("post_hint") or "").lower()

    if data.get("is_self") and hint not in {"image", "hosted:video", "rich:video"}:
        return ""

    # Hosted Reddit video / gallery: the post page is the thing that plays
    if (
        data.get("is_video")
        or data.get("is_gallery")
        or domain == "v.redd.it"
        or "reddit.com/gallery" in dest.lower()
    ):
        return permalink or dest
    if "reddit.com/gallery" in dest.lower():
        return permalink or dest

    if dest.startswith("http") and is_specific_tease_link(dest):
        return dest
    if hint in {"image", "hosted:video", "rich:video", "link"} and permalink:
        if dest.startswith("http") and not _SEARCH_PAGE.search(dest):
            return dest
        return permalink
    if permalink and "/comments/" in permalink and not data.get("is_self"):
        return permalink
    return ""


def _reddit_posts(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        out: list[dict[str, Any]] = []
        for child in data.get("children") or []:
            inner = child.get("data") if isinstance(child, dict) else None
            if isinstance(inner, dict):
                out.append(inner)
        return out
    return []


def reddit_media_from_listing(payload: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for inner in _reddit_posts(payload):
        url = _media_url_from_post(inner)
        if not url or url in seen or not is_specific_tease_link(url):
            continue
        seen.add(url)
        title = re.sub(r"\s+", " ", str(inner.get("title") or "").strip())[:120]
        kind = tease_kind(url)
        item = {
            "title": title or "what you can't have",
            "url": url,
            "kind": kind,
            "duration": "",
        }
        item.update(
            tease_media_fields(
                url=url,
                kind=kind,
                image_url=_reddit_preview_image(inner)
                if kind != "image"
                else url,
                video_url=_reddit_video_url(inner),
            )
        )
        out.append(item)
        if len(out) >= 12:
            break
    return out


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
        if not is_specific_tease_link(url):
            continue
        duration = str(item.get("duration") or item.get("formattedDuration") or "").strip()
        kind = tease_kind(url)
        row = {
            "title": title[:160],
            "url": url,
            "kind": kind,
            "duration": duration,
        }
        row.update(tease_media_fields(url=url, kind=kind))
        out.append(row)
        if len(out) >= 4:
            break
    return out


async def _get_json(client: httpx.AsyncClient, url: str) -> Any:
    try:
        response = await client.get(
            url,
            headers={"User-Agent": _UA, "Accept": "application/json"},
            cookies={"over18": "1"},
        )
        if response.status_code >= 400:
            log.info("Tease HTTP %s for %s", response.status_code, url)
            return None
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001
        log.info("Tease fetch failed for %s", url, exc_info=True)
        return None


async def _fetch_redgifs(client: httpx.AsyncClient, tags: list[str]) -> list[dict[str, str]]:
    auth = await _get_json(client, "https://api.redgifs.com/v2/auth/temporary")
    token = str((auth or {}).get("token") or "").strip()
    if not token:
        return []
    query = genre_query(tags)
    try:
        response = await client.get(
            "https://api.redgifs.com/v2/gifs/search",
            params={"search_text": query, "count": 12},
            headers={
                "User-Agent": _UA,
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        if response.status_code >= 400:
            log.info("Redgifs search HTTP %s", response.status_code)
            return []
        payload = response.json()
        gifs = payload.get("gifs") if isinstance(payload, dict) else []
    except Exception:  # noqa: BLE001
        log.info("Redgifs search failed", exc_info=True)
        return []
    out: list[dict[str, str]] = []
    for gif in gifs or []:
        if not isinstance(gif, dict):
            continue
        gid = str(gif.get("id") or "").strip()
        tags_txt = " ".join(str(t) for t in (gif.get("tags") or []) if t)
        title = str(gif.get("description") or tags_txt or gid).strip()[:120]
        if not gid or _UNSAFE_TITLE.search(title) or _UNSAFE_TITLE.search(tags_txt):
            continue
        url = f"https://www.redgifs.com/watch/{gid}"
        hosts = gif.get("urls") if isinstance(gif.get("urls"), dict) else {}
        item = {
            "title": title or "what you can't have",
            "url": url,
            "kind": "video",
            "duration": str(gif.get("duration") or ""),
        }
        item.update(
            tease_media_fields(
                url=url,
                kind="video",
                image_url=str(
                    (hosts or {}).get("poster")
                    or (hosts or {}).get("thumbnail")
                    or ""
                ),
                video_url=str(
                    (hosts or {}).get("hd") or (hosts or {}).get("sd") or ""
                ),
                embed_url=redgif_iframe(url),
            )
        )
        out.append(item)
        if len(out) >= 8:
            break
    return out


async def fetch_reddit_teases(tags: list[str]) -> list[dict[str, str]]:
    """Reddit posts (via Pullpush) + Redgifs — official reddit.com JSON is 403 now."""
    subs = subs_for_tags(tags)
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def absorb(payload: Any) -> None:
        for item in reddit_media_from_listing(payload):
            url = item["url"]
            if url in seen:
                continue
            seen.add(url)
            found.append(item)

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            pulls = [
                "https://api.pullpush.io/reddit/search/submission/"
                f"?subreddit={sub}&size=25&sort=desc&sort_type=created_utc"
                for sub in subs
            ]
            payloads = await asyncio.gather(
                *[_get_json(client, path) for path in pulls],
                return_exceptions=True,
            )
            for payload in payloads:
                if isinstance(payload, Exception) or payload is None:
                    continue
                absorb(payload)
            for item in await _fetch_redgifs(client, tags):
                url = item["url"]
                if url in seen:
                    continue
                seen.add(url)
                found.append(item)
    except Exception:  # noqa: BLE001
        log.exception("Reddit tease search failed")
    random.shuffle(found)
    return found[:8]


async def fetch_porn_videos(tags: list[str]) -> list[dict[str, str]]:
    """Specific clickable clips/pics — Reddit first, then a Pornhub video if it is not a search."""
    reddit = await fetch_reddit_teases(tags)
    if reddit:
        return reddit
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
    lines = [
        "[TEASE VIDEO — she asked for porn that matches this lock]",
        f"Genre to match: {flavour}.",
        "Adults only. Never anything involving minors.",
        "Pick ONE real Reddit/Redgif/image link. Never a search page. Never invent a URL.",
        "Hands-off for him unless she said otherwise.",
    ]
    if videos:
        lines.append("Use one of these real links:")
        for item in videos:
            dur = f" ({item['duration']})" if item.get("duration") else ""
            lines.append(f"- {item['title']}{dur}: {item['url']}")
    else:
        lines.append(
            "Live Reddit pull missed. Do not invent a clip. Ask her to tap Video again."
        )
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
    kind: str = "",
) -> str:
    clip = (title or "this").strip() or "this"
    link = (url or "").strip()
    pic = (kind or tease_kind(link)).lower() in {"image", "gif", "gallery"}
    verb = "Look at" if pic else "Watch"
    if bull_voice:
        tease = f"{verb} {clip}. Hands off. She's with me. Cage stays on."
    else:
        tease = f"{verb} {clip}. Hands off. Cage stays on. Sit with that ache."
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
