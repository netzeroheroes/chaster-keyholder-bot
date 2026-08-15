from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from app.chaster import BLOCKED_EXTENSION_SLUGS, ChasterClient

log = logging.getLogger(__name__)

ActionKind = Literal[
    "status",
    "add_time",
    "freeze",
    "unfreeze",
    "toggle_freeze",
    "pillory",
    "hide_time",
    "show_time",
    "set_note",
    "history_message",
    "apply_planned",
    "tour_step",
    "list_capabilities",
    "list_kinks",
    "list_history",
    "list_extensions",
    "activate_extension",
    "configure_share_links",
    "configure_hygiene",
    "configure_extension",
    "hygiene_open",
    "request_verification",
    "assign_task",
    "restore_parked_extensions",
    "unsupported_reminders",
    "unsupported_notifications",
]

MUTATING = frozenset(
    {
        "add_time",
        "freeze",
        "unfreeze",
        "toggle_freeze",
        "pillory",
        "hide_time",
        "show_time",
        "set_note",
        "history_message",
        "activate_extension",
        "configure_share_links",
        "configure_hygiene",
        "configure_extension",
        "hygiene_open",
        "request_verification",
        "assign_task",
        "restore_parked_extensions",
    }
)

# Duo Domme partner session — only these actions are real via our bot token
DUO_DOMME_ACTIONS = (
    "add_time",
    "remove_time",
    "freeze",
    "unfreeze",
    "toggle_freeze",
    "pillory",
    "set_display_remaining_time",
)

# Common extensions we can activate on a trusted lock (keyholder edit)
ACTIVATABLE_SLUGS = {
    "jigsaw": "jigsaw-puzzle",
    "jigsaws": "jigsaw-puzzle",
    "puzzle": "jigsaw-puzzle",
    "puzzles": "jigsaw-puzzle",
    "jigsaw puzzle": "jigsaw-puzzle",
    "jigsaw-puzzle": "jigsaw-puzzle",
    "wheel": "wheel-of-fortune",
    "wheel of fortune": "wheel-of-fortune",
    "wheel-of-fortune": "wheel-of-fortune",
    "tasks": "tasks",
    "task": "tasks",
    "dice": "dice",
    "pillory": "pillory",
    # hygiene / temporary-opening is blocked — in-app Request hygiene + R+D box
    "share link": "link",
    "share links": "link",
    "sharelinks": "link",
    "link": "link",
    "links": "link",
    "verification": "verification-picture",
    "verification picture": "verification-picture",
    "verification-picture": "verification-picture",
    "random events": "random-events",
    "random-events": "random-events",
    "guess timer": "guess-timer",
    "guess-timer": "guess-timer",
    "guesstimer": "guess-timer",
}


@dataclass
class ChasterIntent:
    kind: ActionKind
    seconds: int = 0
    reason: str = ""
    title: str = ""
    # Pillory: seconds added per community vote (extension config timeToAdd).
    # Share links: also used as timeToAdd when encoding configs.
    time_to_add: int = 0
    # Share links only: minimum visits (nbVisits) before unlock — real Chaster field.
    votes: int = 0


@dataclass
class ChasterActionResult:
    ok: bool
    facts: str
    error: str = ""
    lock: dict[str, Any] | None = None
    before: dict[str, Any] | None = None
    blocked: bool = False


_TIME_UNIT = r"(?:seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d)"


def extract_duration_seconds(text: str) -> int | None:
    """Find the most relevant duration mention in recent chat text."""
    if not text:
        return None
    low = text.lower()
    # Prefer "add/extend/by X hours" style mentions (last match wins)
    patterned = list(
        re.finditer(
            rf"(?:add|added|adding|extend|extended|extending|by|plus|\+)\s+"
            rf"(\d+(?:\.\d+)?)\s*({_TIME_UNIT})",
            low,
        )
    )
    if patterned:
        m = patterned[-1]
        return _to_seconds(m.group(1), m.group(2))
    # Fallback: last bare duration in the text
    bare = list(re.finditer(rf"(\d+(?:\.\d+)?)\s*({_TIME_UNIT})", low))
    if bare:
        m = bare[-1]
        return _to_seconds(m.group(1), m.group(2))
    return None


def parse_chaster_intent(
    message: str,
    *,
    context: str = "",
) -> ChasterIntent | None:
    text = (message or "").strip()
    if not text:
        return None
    low = text.lower()

    # Capability catalog (real lock controls — Domme menu)
    if re.search(
        r"\b(what can (we|you|i) do|"
        r"what (features|actions|controls)|"
        r"(list|show) (the )?(chaster )?(features|actions|controls)|"
        r"chaster (features|capabilities|actions)|"
        r"what (do we|can we) control|"
        r"options (for|on) (his |the )?lock)\b",
        low,
    ) and re.search(r"\b(lock|cage|chaster|timer|time)\b", low):
        return ChasterIntent(kind="list_capabilities")

    # Extensions / plugins on the lock (must beat kink/toy matching — "toy with him")
    if re.search(
        r"\b(extensions?|plugins?|jigsaws?|puzzles?|wheel(?:\s+of\s+fortune)?|tasks?)\b",
        low,
    ) and re.search(
        r"\b(what|which|list|show|have|on (his |the |my )?lock|use|how|can you do|do (to|with)|control)\b",
        low,
    ):
        return ChasterIntent(kind="list_extensions")

    # Domme: restore plugins parked to free a non-Plus extension slot
    if re.search(
        r"\b(restore|unpark|put back)\b.*\b(parked\s+)?(extensions?|plugins?)\b"
        r"|\brestore parked\b",
        low,
    ):
        return ChasterIntent(kind="restore_parked_extensions")

    # Domme: activate / add an extension on the lock
    act = re.search(
        r"\b(?:activate|enable|add|install|turn on)\b\s+"
        r"(?:the\s+|his\s+|a\s+)?"
        r"(jigsaws?|puzzles?|jigsaw(?:\s+puzzle)?|wheel(?:\s+of\s+fortune)?|"
        r"tasks?|dice|pillory|hygiene(?:\s+opening)?|temporary opening|"
        r"share\s*links?|links?|verification(?:\s+picture)?|random events)\b",
        low,
    )
    if act:
        alias = act.group(1).strip().lower()
        slug = ACTIVATABLE_SLUGS.get(alias) or ACTIVATABLE_SLUGS.get(
            alias.replace(" ", "-")
        )
        if slug:
            return ChasterIntent(kind="activate_extension", reason=slug)

    # Configure hygiene opening duration (openingTime / penalty)
    # e.g. "set hygiene to 10 mins", "hygiene opening time 10 minutes"
    if re.search(
        r"\b(hygiene|temporary opening|temp(?:orary)? (?:unlock|opening)|"
        r"opening time|unlock time|clean(?:ing)? (?:time|window))\b",
        low,
    ) and re.search(rf"\d+(?:\.\d+)?\s*{_TIME_UNIT}", low) and not re.search(
        r"\b(open|start|allow|grant|give)\b.*\b(hygiene|temporary opening)\b"
        r"|\b(open hygiene|grant hygiene)\b",
        low,
    ):
        parts: list[str] = []
        pen_m = re.search(
            rf"penalty\s*(?:time)?\s*(?:to|for|=|:)?\s*"
            rf"(\d+(?:\.\d+)?)\s*({_TIME_UNIT})",
            low,
        )
        open_m = re.search(
            rf"(?:opening|unlock|clean(?:ing)?)\s*(?:time|window|duration)\s*"
            rf"(?:to|for|=|:)?\s*(\d+(?:\.\d+)?)\s*({_TIME_UNIT})",
            low,
        ) or re.search(
            rf"(?:set|change|update|make)\s+(?:the\s+)?(?:hygiene|opening|unlock)\s+"
            rf"(?:time\s+)?(?:to\s+)?(\d+(?:\.\d+)?)\s*({_TIME_UNIT})",
            low,
        ) or re.search(
            rf"hygiene\s+(?:to|for|=|:)\s*(\d+(?:\.\d+)?)\s*({_TIME_UNIT})",
            low,
        )
        if open_m:
            parts.append(f"opening:{_to_seconds(open_m.group(1), open_m.group(2))}")
        if pen_m:
            parts.append(f"penalty:{_to_seconds(pen_m.group(1), pen_m.group(2))}")
        # "hygiene 10 mins" / "hygiene unlock 10 minutes" with no explicit opening/penalty label
        if not parts:
            dur = re.search(rf"(\d+(?:\.\d+)?)\s*({_TIME_UNIT})", low)
            if dur:
                parts.append(f"opening:{_to_seconds(dur.group(1), dur.group(2))}")
        if parts:
            return ChasterIntent(kind="configure_hygiene", reason="|".join(parts))

    # Hygiene opening (temporary unlock) — start the window now
    if re.search(
        r"\b(hygiene|temporary opening|temp(?:orary)? unlock|open (him |the lock )?for (cleaning|hygiene))\b",
        low,
    ) and re.search(r"\b(open|start|allow|grant|give)\b", low):
        return ChasterIntent(kind="hygiene_open")

    # Verification picture request
    if re.search(
        r"\b(request|demand|ask for|send)\b.*\b(verification|verify)\b.*\b(pic|picture|photo)\b"
        r"|\bverification (picture|photo) (request|now)\b"
        r"|\bmake him (verify|send (a )?verification)\b",
        low,
    ):
        return ChasterIntent(kind="request_verification")

    # Assign task via Tasks extension
    task_m = re.search(
        r"\b(?:assign|give|send)\b(?:\s+him)?\s+(?:a\s+)?task\b(?:\s*[:\-]\s*|\s+)(.+)$",
        message.strip(),
        re.I,
    ) or re.search(
        r"\btask him (?:to |with )?(.+)$",
        message.strip(),
        re.I,
    )
    if task_m:
        return ChasterIntent(kind="assign_task", reason=task_m.group(1).strip()[:500])

    # Configure share links (+N / -N per visit, min visits, random)
    if re.search(r"\b(share\s*links?|link extension)\b", low) and re.search(
        r"\b(set|config(?:ure)?|change|update|make|harden)\b",
        low,
    ):
        add_m = re.search(
            rf"\b(?:add|plus|\+)\s*(\d+(?:\.\d+)?)\s*({_TIME_UNIT})\b", low
        )
        rem_m = re.search(
            rf"\b(?:remove|minus|-)\s*(\d+(?:\.\d+)?)\s*({_TIME_UNIT})\b", low
        )
        extras: list[str] = []
        if add_m:
            extras.append(f"add:{_to_seconds(add_m.group(1), add_m.group(2))}")
        if rem_m:
            extras.append(f"remove:{_to_seconds(rem_m.group(1), rem_m.group(2))}")
        visits = _parse_share_min_visits(low)
        if visits is not None:
            extras.append(f"visits:{visits}")
        if re.search(r"\b(enable|with)\s+random\b|\brandom\s+on\b", low):
            extras.append("random:1")
        elif re.search(r"\b(disable|no)\s+random\b|\brandom\s+off\b", low):
            extras.append("random:0")
        if re.search(r"\b(anyone|public|anonymous)\b", low):
            extras.append("logged:0")
        elif re.search(r"\blogged[- ]?in only\b|\bmembers only\b", low):
            extras.append("logged:1")
        return ChasterIntent(
            kind="configure_share_links",
            reason="|".join(extras),
            votes=visits or 0,
        )

    # Configure other plugins creatively (dice / wheel / random-events / tasks…)
    cfg_ext = re.search(
        r"\b(?:set|config(?:ure)?|harden|torment)\b\s+"
        r"(?:the\s+)?"
        r"(dice|wheel(?:\s+of\s+fortune)?|random events?|tasks?|jigsaw(?:\s+puzzle)?|"
        r"guess[- ]?timer|pillory)\b",
        low,
    )
    if cfg_ext:
        slug = ACTIVATABLE_SLUGS.get(cfg_ext.group(1).strip(), "")
        if not slug and "random" in cfg_ext.group(1):
            slug = "random-events"
        if slug == "pillory":
            # Pillory config is applied when starting; still allow explicit set.
            per = _parse_pillory_time_to_add(low)
            return ChasterIntent(
                kind="configure_extension",
                title="pillory",
                reason=_encode_config_parts(
                    {
                        "timeToAdd": per,
                        "limitToLoggedUsers": False,
                    }
                ),
                time_to_add=per,
            )
        if slug == "dice":
            mult = DEFAULT_PILLORY_TIME_TO_ADD
            dm = re.search(
                rf"(?:multiplier|stakes?|per\s+pip)\s*"
                rf"(?:to\s+|=\s*|:\s*)?(\d+(?:\.\d+)?)\s*({_TIME_UNIT})",
                low,
            ) or re.search(rf"(\d+(?:\.\d+)?)\s*({_TIME_UNIT})", low)
            if dm:
                mult = max(60, _to_seconds(dm.group(1), dm.group(2)))
            return ChasterIntent(
                kind="configure_extension",
                title="dice",
                reason=_encode_config_parts({"multiplier": mult}),
            )
        if slug == "random-events":
            diff = "hard"
            if re.search(r"\bexpert\b", low):
                diff = "expert"
            elif re.search(r"\bnormal\b", low):
                diff = "normal"
            elif re.search(r"\beasy\b", low):
                diff = "easy"
            return ChasterIntent(
                kind="configure_extension",
                title="random-events",
                reason=_encode_config_parts({"difficulty": diff}),
            )
        if slug == "wheel-of-fortune":
            return ChasterIntent(
                kind="configure_extension",
                title="wheel-of-fortune",
                reason="torment:1",
            )
        if slug == "tasks":
            return ChasterIntent(
                kind="configure_extension",
                title="tasks",
                reason="torment:1",
            )
        if slug == "jigsaw-puzzle":
            return ChasterIntent(
                kind="configure_extension",
                title="jigsaw-puzzle",
                reason="torment:1",
            )
        if slug == "guess-timer":
            return ChasterIntent(
                kind="configure_extension",
                title="guess-timer",
                reason="torment:1",
            )

    if re.search(
        r"\b((lock\s+)?history|recent (lock )?actions?|what happened on (his |the )?lock|"
        r"show (me )?(the )?history|last (lock )?events?)\b",
        low,
    ):
        return ChasterIntent(kind="list_history")

    # Catalog only — "pick N toys / create a scene" is handled by scene_builder
    # Avoid matching "toy with him" (verb) — require kink/profile catalog language
    if (
        (
            re.search(
                r"\b(kinks?|fetish(?:es)?|his profile|kink profile)\b",
                low,
            )
            or re.search(r"\b(his|the)\s+toys?\b", low)
            or re.search(r"\btoys?\s+(listed|on file|available|does he have)\b", low)
        )
        and re.search(
            r"\b(what|list|show|profile|available)\b",
            low,
        )
        and not re.search(
            r"\b(pick|create|build|scene|use\s+\d+|extensions?|plugins?|toy with)\b",
            low,
        )
    ):
        return ChasterIntent(kind="list_kinks")

    # Tour / stepwise — handled in chat_service via chaster_tour
    if re.search(
        r"\b((?:try|do|test|run)\s+(?:these\s+)?features?\b|"
        r"(?:one|1)\s*by\s*(?:one|1)|in\s+turn|each\s+one|"
        r"one\s+at\s+a\s+time|step\s+by\s+step)\b",
        low,
    ) or re.fullmatch(
        r"\s*(next|continue|go\s+on|and\s+the\s+next|do\s+the\s+next(?:\s+one)?)\s*[.!]?\s*",
        low,
    ):
        return ChasterIntent(kind="tour_step", reason=context or text)

    if re.search(
        r"\b((?:do|apply|run)\s+(?:them|those|these|each|it)|"
        r"start\s+with\s+(?:the\s+)?visibility|"
        r"apply\s+(?:the\s+)?(?:plan|changes|settings))\b",
        low,
    ):
        return ChasterIntent(kind="apply_planned", reason=context or text)

    if re.search(r"\b(reminder|reminders)\b", low) and re.search(
        r"\b(set|enable|change|notification|notif)\b", low
    ):
        return ChasterIntent(kind="unsupported_reminders")

    # History message → lock history (push-notifies lockee via custom log)
    history = _parse_history_message(text)
    if history:
        return history

    # Legacy "custom notification" wording → try as history message if body present
    if re.search(r"\b(custom\s+)?notification(s)?\b", low) and re.search(
        r"\b(set|enable|change|custom|message|send|push)\b", low
    ):
        body = re.sub(
            r".*?\b(?:notification|message|push)\b[:\s]*",
            "",
            text,
            count=1,
            flags=re.I,
        ).strip(" '\"")
        if body and len(body) > 2:
            return ChasterIntent(
                kind="history_message",
                title="Message from your keyholders",
                reason=body[:2000],
            )
        return ChasterIntent(kind="unsupported_notifications")

    if re.search(r"\b(toggle\s+freeze|freeze\s+toggle)\b", low):
        return ChasterIntent(kind="toggle_freeze")
    if re.search(r"\bunfreeze\b", low):
        return ChasterIntent(kind="unfreeze")
    if re.search(r"\bfreeze\b", low):
        return ChasterIntent(kind="freeze")

    if re.search(
        r"\b(hide|conceal|hidden|invisible|visibility)\b",
        low,
    ) and re.search(r"\b(time|timer|lock|cage)\b", low):
        if re.search(r"\b(show|reveal|unhide|visible)\b", low) and not re.search(
            r"\b(hide|hidden|invisible)\b", low
        ):
            return ChasterIntent(kind="show_time")
        return ChasterIntent(kind="hide_time")
    if re.search(r"\b(show|reveal|unhide)\b.*\b(time|timer)\b", low) or re.search(
        r"\b(time|timer)\b.*\b(show|visible)\b", low
    ):
        return ChasterIntent(kind="show_time")

    note_m = re.search(
        r"\b(?:add|set|write)\s+(?:a\s+)?(?:keyholder\s+)?note\b(?:\s*[:=]\s*|\s+)(.+)$",
        text,
        re.I,
    )
    if note_m:
        return ChasterIntent(kind="set_note", reason=note_m.group(1).strip(" '\"")[:10000])

    if re.search(r"\bpillory\b", low):
        # Prefer explicit window: "for 10 minutes" (not the per-vote duration).
        dur = re.search(
            rf"(?:for|window|duration)\s+(\d+(?:\.\d+)?)\s*({_TIME_UNIT})",
            low,
        ) or re.search(rf"(\d+(?:\.\d+)?)\s*({_TIME_UNIT})", low)
        secs = 300
        if dur:
            # If the only duration is clearly "per vote", keep default window.
            span = low[dur.start() : dur.end() + 12]
            if not re.search(r"\bper\s+vote\b|\beach\s+vote\b", span):
                secs = max(300, _to_seconds(dur.group(1), dur.group(2)))
        per_vote = _parse_pillory_time_to_add(low)
        reason = "AI Domme punishment"
        reason_m = re.search(r"\b(?:because|reason:?)\s+(.+)$", low)
        if reason_m:
            reason = reason_m.group(1).strip()
        else:
            cleaned = re.sub(r"\bpillory\b", " ", low)
            cleaned = re.sub(rf"\d+(?:\.\d+)?\s*{_TIME_UNIT}", " ", cleaned)
            cleaned = re.sub(
                r"\b(?:per|each|a)\s+vote\b|\bvotes?\b|\btime\s*to\s*add\b",
                " ",
                cleaned,
            )
            cleaned = re.sub(r"\b(him|boy|for|to|the|a|an|with|window|duration)\b", " ", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,!")
            if cleaned:
                reason = cleaned
        return ChasterIntent(
            kind="pillory",
            seconds=secs,
            reason=reason,
            time_to_add=per_vote,
        )

    add = re.search(
        rf"\b(?:add|plus|\+|apply|put)\s+(?:that\s+|the\s+|this\s+|his\s+)?"
        rf"(\d+(?:\.\d+)?)\s*({_TIME_UNIT})\b",
        low,
    ) or re.search(
        rf"\b(\d+(?:\.\d+)?)\s*({_TIME_UNIT})\s*(?:to|onto|on)\s+(?:his|the)?\s*lock\b",
        low,
    )
    if add:
        return ChasterIntent(kind="add_time", seconds=_to_seconds(add.group(1), add.group(2)))

    # Bare duration replies: "10 mins", "+10m", "2 hours."
    bare = re.fullmatch(
        rf"\s*[+]?\s*(\d+(?:\.\d+)?)\s*({_TIME_UNIT})\s*[.!]?\s*",
        low,
    )
    ctx_low = (context or "").lower()
    if bare:
        secs = _to_seconds(bare.group(1), bare.group(2))
        # If recent chat was about hygiene opening, set openingTime — not lock add
        if re.search(
            r"\b(hygiene|temporary opening|opening time|unlock time|"
            r"clean(?:ing)? (?:time|window)|how long .{0,20}hygiene|"
            r"hygiene unlock)\b",
            ctx_low,
        ):
            return ChasterIntent(kind="configure_hygiene", reason=f"opening:{secs}")
        return ChasterIntent(kind="add_time", seconds=secs)

    # "add that time" / "add the time for him" — resolve duration from recent chat
    if re.search(
        r"\b(?:add|apply|put)\s+(?:that|the|this)\s+time\b"
        r"|\badd\s+it\b"
        r"|\bdo\s+(?:the\s+)?(?:time|add(?:ition)?)\b",
        low,
    ):
        secs = extract_duration_seconds(message) or extract_duration_seconds(context)
        if secs and secs > 0:
            return ChasterIntent(kind="add_time", seconds=secs)
        try:
            from app.runtime_controls import get_controls

            c = get_controls()
            secs = int(c.max_add_time_seconds or c.default_add_time_seconds or 3600)
        except Exception:  # noqa: BLE001
            secs = 3600
        return ChasterIntent(kind="add_time", seconds=max(60, secs))

    # Follow-up duration after hygiene discussion
    if extract_duration_seconds(message) and re.search(
        r"\b(hygiene|temporary opening|opening time|unlock time)\b",
        ctx_low,
    ):
        secs = extract_duration_seconds(message)
        if secs and secs > 0:
            return ChasterIntent(kind="configure_hygiene", reason=f"opening:{secs}")

    # Follow-up: Domme answers with a duration after someone asked to add/extend time
    if extract_duration_seconds(message) and re.search(
        r"\b(add|added|adding|extend|extended|how much|how long|time)\b",
        ctx_low,
    ):
        secs = extract_duration_seconds(message)
        if secs and secs > 0:
            return ChasterIntent(kind="add_time", seconds=secs)

    # Bare "add time" / "add some time" / soft|hard — session min/max
    # (lock/cage optional — Sub/Domme often just say "add some time")
    if re.search(
        r"\b(add|plus|\+)\b\s*"
        r"(some|more|a\s+little|a\s+bit|extra|soft|hard|small|gentle|min(?:imum)?|max(?:imum)?)?\s*"
        r"time\b"
        r"|\bextend (him|the lock|his (lock|cage)|me)\b"
        r"|\b(more|extra)\s+time\b",
        low,
    ):
        try:
            from app.runtime_controls import get_controls

            c = get_controls()
            lo = int(c.min_add_time_seconds or c.soft_add_time_seconds or 900)
            hi = int(c.max_add_time_seconds or c.hard_add_time_seconds or 86400)
            if re.search(r"\b(soft|small|little|gentle|minimum|min|bit)\b", low):
                secs = lo
            else:
                secs = hi
        except Exception:  # noqa: BLE001
            secs = 3600
        return ChasterIntent(kind="add_time", seconds=max(60, secs))

    remove = re.search(
        rf"\b(?:remove|subtract|minus|-)\s*(\d+(?:\.\d+)?)\s*({_TIME_UNIT})\b",
        low,
    )
    if remove and re.search(r"\b(lock|cage|chaster|time)\b", low):
        return ChasterIntent(
            kind="add_time",
            seconds=-_to_seconds(remove.group(1), remove.group(2)),
        )

    if re.search(
        r"\b(how much|how long|remaining|left on|time (?:on|left)|lock time|"
        r"what(?:'s| is) (?:his |the )?lock|check (?:his |the )?lock)\b",
        low,
    ) and re.search(r"\b(lock|cage|chaster|time|timer)\b", low):
        return ChasterIntent(kind="status")

    return None


def _parse_history_message(text: str) -> ChasterIntent | None:
    """Domme/AI: post a message onto his lock history (custom log / push)."""
    patterns = [
        r"\b(?:send|post|leave|write)\s+(?:him\s+)?(?:a\s+)?(?:lock\s+)?(?:history\s+)?message\b",
        r"\b(?:message|notify|ping)\s+(?:him|the\s+(?:lock|boy|sub|wearer))\b",
        r"\b(?:push\s+(?:notify|notification)|history\s+message|lock\s+message)\b",
        r"\b(?:tell|message)\s+(?:his|the)\s+lock\b",
        r"\bpost\s+to\s+(?:his|the)\s+history\b",
    ]
    if not any(re.search(p, text, re.I) for p in patterns):
        return None

    default_title = "Message from your keyholders"
    payload = ""

    # Prefer explicit separator after the command phrase
    for pat in (
        r"\b(?:send|post|leave|write)\s+(?:him\s+)?(?:a\s+)?"
        r"(?:lock\s+)?(?:history\s+)?message\s*[:\-]\s*(.+)$",
        r"\b(?:message|notify|ping)\s+(?:him|the\s+(?:lock|boy|sub|wearer))"
        r"(?:\s+that|\s+to)?\s*[:\-]?\s*(.+)$",
        r"\b(?:push\s+(?:notify|notification)|history\s+message|lock\s+message)"
        r"\s*[:\-]\s*(.+)$",
        r"\b(?:tell|message)\s+(?:his|the)\s+lock\s*[:\-]\s*(.+)$",
        r"\bpost\s+to\s+(?:his|the)\s+history\s*[:\-]\s*(.+)$",
    ):
        m = re.search(pat, text, re.I | re.S)
        if m:
            payload = m.group(1).strip().strip(" '\"")
            break

    if not payload:
        return ChasterIntent(kind="history_message", title="", reason="")

    title = default_title
    body = payload
    # Only | splits title/body (colon is common in "message him: text")
    if "|" in payload:
        left, right = payload.split("|", 1)
        if left.strip() and right.strip():
            title, body = left.strip()[:200], right.strip()

    return ChasterIntent(kind="history_message", title=title, reason=body[:2000])


def _to_seconds(amount: str, unit: str) -> int:
    n = float(amount)
    u = unit.lower()
    if u.startswith("d"):
        return int(n * 86400)
    if u.startswith("h"):
        return int(n * 3600)
    if u.startswith("m"):
        return int(n * 60)
    return int(n)


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    neg = seconds < 0
    s = abs(int(seconds))
    days, rem = divmod(s, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    if secs and not days and not hours:
        parts.append(f"{secs}s")
    out = " ".join(parts)
    return f"-{out}" if neg else out


# Pillory extension: time added per community vote (catalog default is 1h).
# Start small at 10 minutes so a pile-on still hurts without nuking the lock.
DEFAULT_PILLORY_TIME_TO_ADD = 600
# Share links: minimum visits before unlock (real nbVisits field).
DEFAULT_SHARE_MIN_VISITS = 10


def _parse_pillory_time_to_add(low: str) -> int:
    """Parse per-vote add: '10 minutes per vote', 'vote add 10m', 'timeToAdd 600'."""
    m = re.search(
        rf"(?:per\s+vote|each\s+vote|vote\s+adds?|time\s*to\s*add|timetoadd)"
        rf"\s*(?:of\s+|is\s+|to\s+|=\s*|:\s*)?"
        rf"(\d+(?:\.\d+)?)\s*({_TIME_UNIT})"
        rf"|(\d+(?:\.\d+)?)\s*({_TIME_UNIT})\s*(?:per|each|a)\s+vote",
        low,
    )
    if not m:
        return DEFAULT_PILLORY_TIME_TO_ADD
    if m.group(1) and m.group(2):
        secs = _to_seconds(m.group(1), m.group(2))
    else:
        secs = _to_seconds(m.group(3), m.group(4))
    return max(60, min(86400, int(secs)))


def _parse_share_min_visits(low: str) -> int | None:
    """Parse share-link minimum visits/votes required (nbVisits)."""
    m = re.search(
        r"\b(?:with\s+|need(?:ing)?\s+|require(?:s|d)?\s+|min(?:imum)?\s+)?"
        r"(\d{1,3})\s*(?:visits?|votes?)(?:\s+required)?\b"
        r"|\b(?:visits?|votes?|nbvisits?)\s*(?:required\s*)?[=:]?\s*(\d{1,3})\b",
        low,
    )
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    return max(0, min(100, int(raw)))


def _encode_config_parts(parts: dict[str, Any]) -> str:
    out: list[str] = []
    for k, v in parts.items():
        if v is None:
            continue
        if isinstance(v, bool):
            out.append(f"{k}:{'1' if v else '0'}")
        else:
            out.append(f"{k}:{v}")
    return "|".join(out)


def _decode_config_parts(reason: str) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for part in (reason or "").split("|"):
        if ":" not in part:
            continue
        key, raw = part.split(":", 1)
        key = key.strip()
        raw = raw.strip()
        if not key:
            continue
        if raw in ("1", "true", "yes"):
            updates[key] = True
        elif raw in ("0", "false", "no"):
            updates[key] = False
        else:
            try:
                updates[key] = int(raw)
            except ValueError:
                updates[key] = raw
    return updates


def json_dumps_safe(obj: Any) -> str:
    import json

    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return str(obj)


def _torment_wheel_segments() -> list[dict[str, Any]]:
    """Harsh wheel: mostly add/freeze/pillory, tiny remove, cruel text."""
    return [
        {"type": "add-time", "text": "More cage time", "duration": 7200},
        {"type": "add-time", "text": "Stack another hour", "duration": 3600},
        {"type": "freeze", "text": "Frozen for Dommes", "duration": 3600},
        {"type": "pillory", "text": "Public shame", "duration": 900},
        {"type": "text", "text": "Edge twice. No release. Report when done.", "duration": 0},
        {"type": "remove-time", "text": "Tiny mercy", "duration": 300},
    ]


def _torment_config_for(
    slug: str, reason: str, intent: ChasterIntent
) -> dict[str, Any]:
    """Build real extension config updates from catalog-backed fields only."""
    s = (slug or "").strip()
    parts = _decode_config_parts(reason)
    if s == "pillory":
        return {
            "timeToAdd": int(
                parts.get("timeToAdd")
                or intent.time_to_add
                or DEFAULT_PILLORY_TIME_TO_ADD
            ),
            "limitToLoggedUsers": bool(parts.get("limitToLoggedUsers", False)),
        }
    if s == "dice":
        return {
            "multiplier": int(parts.get("multiplier") or 7200),
            "nbSides": int(parts.get("nbSides") or 6),
        }
    if s == "random-events":
        diff = str(parts.get("difficulty") or "hard")
        if diff not in ("easy", "normal", "hard", "expert"):
            diff = "hard"
        return {"difficulty": diff}
    if s == "wheel-of-fortune":
        return {"segments": _torment_wheel_segments()}
    if s == "tasks":
        # Deny wearer self-edits; Domme/AI keep assign path via Tasks API.
        return {
            "allowWearerToEditTasks": False,
            "allowWearerToConfigureTasks": False,
            "preventWearerFromAssigningTasks": True,
            "allowWearerToChooseTasks": False,
            "voteEnabled": True,
            "voteDuration": 21600,
        }
    if s == "jigsaw-puzzle":
        return {
            "pieces": 120,
            "timeLimit": 900,
            "timeLimitActive": True,
            "freezeWhenAvailable": True,
            "preventUnlockingWhenAvailable": True,
            "randomOrder": True,
            "punishments": [{"action": "ADD_TIME", "data": 30}],
        }
    if s == "guess-timer":
        return {"minRandomTime": 21600, "maxRandomTime": 86400}
    if s == "temporary-opening":
        return {
            "openingTime": int(parts.get("openingTime") or 300),
            "penaltyTime": int(parts.get("penaltyTime") or 86400),
            "freezeLockWhileOpen": True,
            "requireVerificationPictureAfter": True,
            "allowOnlyKeyholderToOpen": False,
        }
    if s == "verification-picture":
        return {"visibility": "all", "triggerInitialVerification": False}
    # Fall through: apply decoded parts if they look like config keys
    known = {
        k: v
        for k, v in parts.items()
        if k
        not in (
            "torment",
            "add",
            "remove",
            "visits",
            "random",
            "logged",
            "visible",
        )
    }
    return known


def remaining_seconds(lock: dict[str, Any]) -> int | None:
    end = lock.get("endDate")
    if not end:
        return None
    end_dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
    return int((end_dt - datetime.now(timezone.utc)).total_seconds())


def summarize_lock(lock: dict[str, Any]) -> dict[str, Any]:
    user = lock.get("user") or {}
    rem = remaining_seconds(lock)
    status = str(lock.get("status") or "unknown")
    display = bool(lock.get("displayRemainingTime", True))
    if rem is None and not display:
        remaining_label = "hidden"
    else:
        remaining_label = format_duration(rem)
    return {
        "lock_id": lock.get("_id") or lock.get("id"),
        "status": status,
        "is_frozen": bool(lock.get("isFrozen")),
        "is_test_lock": bool(lock.get("isTestLock")),
        "display_remaining_time": display,
        "username": user.get("username"),
        "end_date": lock.get("endDate"),
        "remaining_seconds": rem,
        "remaining": remaining_label,
        "timer_ended": bool(rem is not None and rem <= 0),
        "actionable": status == "locked",
    }


def _status_lines(label: str, summary: dict[str, Any]) -> str:
    rem = summary.get("remaining") or "unknown"
    rem_secs = summary.get("remaining_seconds")
    if rem_secs is None:
        rem_detail = "seconds unknown (timer may be hidden)"
    else:
        rem_detail = f"{rem_secs} seconds"
    return (
        f"{label}:\n"
        f"- Wearer: {summary.get('username') or '?'}\n"
        f"- Status: {summary.get('status')}\n"
        f"- Remaining: {rem} ({rem_detail})\n"
        f"- Frozen: {summary.get('is_frozen')}\n"
        f"- Timer visible: {summary.get('display_remaining_time')}\n"
        f"- Timer ended: {summary.get('timer_ended')}\n"
        f"- End (UTC): {summary.get('end_date')}\n"
        f"- Lock id: {summary.get('lock_id')}\n"
        f"- Test lock: {summary.get('is_test_lock')}"
    )


async def fetch_live_status_block(
    chaster: ChasterClient, *, requested_by: str = "system"
) -> str:
    """Fresh lock snapshot for every chat turn — never invent numbers from memory."""
    lock = await resolve_lock(chaster)
    lock = await refresh_lock(chaster, lock)
    current = summarize_lock(lock)
    return (
        "CHASTER LIVE STATUS (real API this turn — ONLY source of lock numbers):\n"
        f"- Requested context by: {requested_by}\n"
        f"{_status_lines('CURRENT', current)}\n"
        "Quote remaining time EXACTLY as above. "
        "Never invent days/hours, totals, keypad codes, or 'new length'. "
        "If you change the lock, emit [[[LOCK]]] tags so the API runs — "
        "do not narrate fake changes."
    )


def _facts_after(
    *,
    action_line: str,
    before: dict[str, Any],
    after: dict[str, Any],
    requested_by: str,
) -> str:
    return (
        f"CHASTER ACTION DONE (Duo Domme extension API):\n"
        f"- Requested by: {requested_by}\n"
        f"- Action: {action_line}\n"
        f"{_status_lines('BEFORE', before)}\n"
        f"{_status_lines('AFTER', after)}\n"
        "Use ONLY these numbers. Do not invent durations. "
        "Acknowledge who requested the action."
    )


async def resolve_lock(chaster: ChasterClient) -> dict[str, Any]:
    preferred = (chaster.settings.chaster_lock_id or "").strip()
    if preferred:
        lock = await chaster.get_lock(preferred)
        if lock:
            return lock

    sessions = await chaster.search_extension_sessions()
    for session in sessions:
        lock = session.get("lock")
        if isinstance(lock, dict) and lock.get("_id"):
            # Refresh from lock endpoint so status is current
            fresh = await chaster.get_lock(str(lock["_id"]))
            return fresh or lock

    own = await chaster.list_own_locks()
    for lock in own:
        if lock.get("status") == "locked":
            return lock
    if own:
        return own[0]

    wearers = await chaster.search_wearers(status="locked", limit=20)
    locks = (wearers or {}).get("locks") or []
    if locks:
        return locks[0]
    raise RuntimeError("No Chaster lock found for this token")


async def refresh_lock(chaster: ChasterClient, lock: dict[str, Any]) -> dict[str, Any]:
    lock_id = str(lock.get("_id") or lock.get("id") or "")
    if not lock_id:
        return lock
    fresh = await chaster.get_lock(lock_id)
    return fresh or lock


def preflight_block_reason(intent: ChasterIntent, before: dict[str, Any]) -> str | None:
    """Return a reason to refuse a mutating action, or None if OK to proceed."""
    if intent.kind not in MUTATING:
        return None
    status = str(before.get("status") or "")
    if status != "locked":
        return (
            f"Lock status is '{status or 'unknown'}' (not locked). "
            "Refusing the action until there is an active locked session."
        )
    if intent.kind == "freeze" and before.get("is_frozen"):
        return "Lock is already frozen — no change needed."
    if intent.kind == "unfreeze" and not before.get("is_frozen"):
        return "Lock is already unfrozen — no change needed."
    if intent.kind == "hide_time" and not before.get("display_remaining_time"):
        return "Timer is already hidden — no change needed."
    if intent.kind == "show_time" and before.get("display_remaining_time"):
        return "Timer is already visible — no change needed."
    return None


async def run_chaster_intent(
    chaster: ChasterClient,
    intent: ChasterIntent,
    *,
    requested_by: str = "Domme",
) -> ChasterActionResult:
    try:
        lock = await resolve_lock(chaster)
        lock = await refresh_lock(chaster, lock)
        before = summarize_lock(lock)
        lock_id = str(before["lock_id"])

        log.info(
            "Chaster preflight by=%s intent=%s status=%s remaining=%s frozen=%s",
            requested_by,
            intent.kind,
            before["status"],
            before["remaining"],
            before["is_frozen"],
        )

        if intent.kind == "status":
            facts = (
                f"CHASTER LIVE STATUS (real API — do not invent):\n"
                f"- Requested by: {requested_by}\n"
                f"{_status_lines('CURRENT', before)}\n"
                "Answer with this remaining time accurately. "
                "Acknowledge who asked."
            )
            return ChasterActionResult(ok=True, facts=facts, lock=before, before=before)

        if intent.kind == "list_capabilities":
            return ChasterActionResult(
                ok=True,
                facts=capabilities_text(before, requested_by=requested_by),
                lock=before,
                before=before,
            )

        if intent.kind == "list_kinks":
            username = str(before.get("username") or "").strip()
            if not username:
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=before,
                    facts="Mistress — I couldn't find his profile name on the lock.",
                )
            try:
                profile = await chaster.get_user_kink_profile(username)
            except Exception as exc:  # noqa: BLE001
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=before,
                    facts=(
                        f"Mistress — I couldn't open {username}'s kink profile. "
                        f"({exc})"
                    ),
                )
            return ChasterActionResult(
                ok=True,
                facts=format_kink_profile(username, profile),
                lock=before,
                before=before,
            )

        if intent.kind == "list_history":
            lock_id = str(before.get("lock_id") or "")
            try:
                events = await chaster.get_lock_history(lock_id, limit=12)
            except Exception as exc:  # noqa: BLE001
                return ChasterActionResult(
                    ok=False,
                    error=str(exc),
                    before=before,
                    lock=before,
                    facts=f"Could not load lock history: {exc}",
                )
            from app.lock_watch import format_history_event

            lines = [
                _domme_lock_snapshot(before),
                "",
                "Recent lock history (newest first):",
            ]
            if not events:
                lines.append("(no recent events)")
            for ev in events[:12]:
                lines.append(f"• {format_history_event(ev)}")
            lines.append(
                "I also watch this live — new extension/share/timer events "
                "get a reaction in group chat."
            )
            return ChasterActionResult(
                ok=True,
                facts="\n".join(lines),
                lock=before,
                before=before,
            )

        if intent.kind == "list_extensions":
            lock_id = str(before.get("lock_id") or "")
            try:
                exts = await chaster.list_lock_extensions(lock_id)
            except Exception as exc:  # noqa: BLE001
                return ChasterActionResult(
                    ok=False,
                    error=str(exc),
                    before=before,
                    lock=before,
                    facts=f"Could not list extensions: {exc}",
                )
            facts = format_extensions_facts(before, exts, requested_by=requested_by)
            return ChasterActionResult(
                ok=True,
                facts=facts,
                lock=before,
                before=before,
            )

        if intent.kind == "restore_parked_extensions":
            lock_id = str(before.get("lock_id") or "")
            try:
                result = await chaster.restore_parked_extensions(lock_id)
            except Exception as exc:  # noqa: BLE001
                return ChasterActionResult(
                    ok=False,
                    error=str(exc),
                    before=before,
                    lock=before,
                    facts=f"Could not restore parked extensions: {exc}",
                )
            after_lock = summarize_lock(await refresh_lock(chaster, lock))
            restored = result.get("restored") or []
            still = result.get("still_parked") or []
            names = ", ".join(
                str(e.get("slug") or "?") for e in (result.get("extensions") or [])
            )
            if not restored and not still:
                facts = (
                    f"No parked extensions to restore.\n"
                    f"On lock now: {names or '(none)'}\n"
                    f"{_status_lines('AFTER', after_lock)}"
                )
            else:
                facts = (
                    f"CHASTER ACTION DONE (restore parked):\n"
                    f"- Requested by: {requested_by}\n"
                    f"- Restored: {', '.join(restored) or '(none — still at free 3-slot limit?)'}\n"
                    f"- Still parked: {', '.join(str(p.get('slug') or '?') for p in still) or '(none)'}\n"
                    f"- Extensions now: {names or '(none)'}\n"
                    f"{_status_lines('AFTER', after_lock)}"
                )
            return ChasterActionResult(
                ok=True,
                facts=facts,
                lock=after_lock,
                before=before,
            )

        if intent.kind == "activate_extension":
            lock_id = str(before.get("lock_id") or "")
            slug = (intent.reason or "").strip()
            if slug in BLOCKED_EXTENSION_SLUGS:
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=before,
                    facts=(
                        "Chaster hygiene (temporary-opening) stays off. "
                        "Lockee uses Request hygiene here; you approve; he unlocks/relocks the box."
                    ),
                )
            if not slug:
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=before,
                    facts=(
                        "No extension slug given. Try: activate jigsaw / add share links / "
                        "enable tasks / enable verification picture / enable pillory. "
                        "Hygiene plugin is blocked — use Request hygiene in this chat."
                    ),
                )
            try:
                ensured = await chaster.ensure_extension(
                    lock_id, slug, park_if_needed=True
                )
                after_exts = list(ensured.get("extensions") or [])
                parked = list(ensured.get("parked") or [])
            except Exception as exc:  # noqa: BLE001
                return ChasterActionResult(
                    ok=False,
                    error=str(exc),
                    before=before,
                    lock=before,
                    facts=f"Could not activate `{slug}`: {exc}",
                )
            after_lock = summarize_lock(await refresh_lock(chaster, lock))
            names = ", ".join(
                str(e.get("slug") or "?") for e in after_exts
            ) or "(none)"
            park_line = ""
            if parked:
                park_line = (
                    "- Parked to free a slot (free max 3 extensions): "
                    + ", ".join(str(p.get("slug") or "?") for p in parked)
                    + '. Say "restore parked extensions" later.\n'
                )
            facts = (
                f"CHASTER ACTION DONE (extensions edit):\n"
                f"- Requested by: {requested_by}\n"
                f"- Action: activated / ensured `{slug}` on the lock\n"
                f"{park_line}"
                f"- Extensions now: {names}\n"
                f"{_status_lines('AFTER', after_lock)}\n"
                + _activation_followup(slug)
            )
            return ChasterActionResult(
                ok=True,
                facts=facts,
                lock=after_lock,
                before=before,
            )

        if intent.kind == "hygiene_open":
            return ChasterActionResult(
                ok=True,
                blocked=True,
                before=before,
                lock=before,
                facts=(
                    "Chaster hygiene opening is blocked. "
                    "Lockee taps Request hygiene; keyholder approves; then Unlock / Relock."
                ),
            )

        if intent.kind == "request_verification":
            lock_id = str(before.get("lock_id") or "")
            try:
                await chaster.request_verification_picture(
                    lock_id, actor="keyholder"
                )
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                if "not found" in msg.lower():
                    return ChasterActionResult(
                        ok=True,
                        blocked=True,
                        before=before,
                        lock=before,
                        facts=(
                            "Verification picture extension is not on the lock. "
                            'Say: "activate verification picture".'
                        ),
                    )
                if "already pending" in msg.lower():
                    return ChasterActionResult(
                        ok=True,
                        blocked=True,
                        before=before,
                        lock=before,
                        facts="A verification picture request is already pending.",
                    )
                return ChasterActionResult(
                    ok=False,
                    error=msg,
                    before=before,
                    lock=before,
                    facts=f"Could not request verification: {msg}",
                )
            after = summarize_lock(await refresh_lock(chaster, lock))
            return ChasterActionResult(
                ok=True,
                facts=_facts_after(
                    action_line="Requested a verification picture from the wearer.",
                    before=before,
                    after=after,
                    requested_by=requested_by,
                ),
                lock=after,
                before=before,
            )

        if intent.kind == "assign_task":
            lock_id = str(before.get("lock_id") or "")
            task_text = (intent.reason or "").strip() or "Obey Mistress"
            try:
                await chaster.assign_task(
                    lock_id, task=task_text, points=1, actor="keyholder"
                )
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                if "not found" in msg.lower():
                    return ChasterActionResult(
                        ok=True,
                        blocked=True,
                        before=before,
                        lock=before,
                        facts=(
                            "Tasks extension is not on the lock. "
                            'Say: "activate tasks" first, then assign a task.'
                        ),
                    )
                return ChasterActionResult(
                    ok=False,
                    error=msg,
                    before=before,
                    lock=before,
                    facts=f"Could not assign task: {msg}",
                )
            after = summarize_lock(await refresh_lock(chaster, lock))
            return ChasterActionResult(
                ok=True,
                facts=_facts_after(
                    action_line=f"Assigned Tasks extension task: {task_text}",
                    before=before,
                    after=after,
                    requested_by=requested_by,
                ),
                lock=after,
                before=before,
            )

        if intent.kind == "configure_hygiene":
            return ChasterActionResult(
                ok=True,
                blocked=True,
                before=before,
                lock=before,
                facts=(
                    "Chaster hygiene config is blocked. "
                    "Set allowed unlock time in Settings → Hygiene."
                ),
            )

        if intent.kind == "configure_share_links":
            lock_id = str(before.get("lock_id") or "")
            raw = _decode_config_parts(intent.reason or "")
            updates: dict[str, Any] = {}
            if "add" in raw:
                updates["timeToAdd"] = int(raw["add"])
            if "remove" in raw:
                updates["timeToRemove"] = int(raw["remove"])
            if "timeToAdd" in raw:
                updates["timeToAdd"] = int(raw["timeToAdd"])
            if "timeToRemove" in raw:
                updates["timeToRemove"] = int(raw["timeToRemove"])
            if "visits" in raw or "nbVisits" in raw:
                updates["nbVisits"] = int(raw.get("visits", raw.get("nbVisits")))
            elif intent.votes:
                updates["nbVisits"] = int(intent.votes)
            if "random" in raw or "enableRandom" in raw:
                updates["enableRandom"] = bool(
                    raw.get("random", raw.get("enableRandom"))
                )
            if "logged" in raw or "limitToLoggedUsers" in raw:
                updates["limitToLoggedUsers"] = bool(
                    raw.get("logged", raw.get("limitToLoggedUsers"))
                )
            if "visible" in raw or "visibleOnProfile" in raw:
                updates["visibleOnProfile"] = bool(
                    raw.get("visible", raw.get("visibleOnProfile"))
                )
            if not updates:
                updates = {
                    "timeToAdd": 3600,
                    "timeToRemove": 300,
                    "nbVisits": DEFAULT_SHARE_MIN_VISITS,
                    "enableRandom": True,
                    "limitToLoggedUsers": False,
                }
            try:
                before_exts = await chaster.list_lock_extensions(lock_id)
            except Exception as exc:  # noqa: BLE001
                return ChasterActionResult(
                    ok=False,
                    error=str(exc),
                    before=before,
                    lock=before,
                    facts=f"Could not read extensions: {exc}",
                )
            before_link = next(
                (e for e in before_exts if str(e.get("slug") or "") == "link"),
                None,
            )
            if not before_link:
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=before,
                    facts=(
                        "Share links (`link`) is not on the lock. "
                        'Say: "activate share links" first.'
                    ),
                )
            before_cfg = dict(before_link.get("config") or {})
            try:
                after_exts = await chaster.update_extension_config(
                    lock_id, "link", updates
                )
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                if "not on the lock" in msg.lower() or "activate" in msg.lower():
                    return ChasterActionResult(
                        ok=True,
                        blocked=True,
                        before=before,
                        lock=before,
                        facts=(
                            "Share links (`link`) is not on the lock. "
                            'Say: "activate share links" first.'
                        ),
                    )
                return ChasterActionResult(
                    ok=False,
                    error=msg,
                    before=before,
                    lock=before,
                    facts=f"Could not configure share links: {msg}",
                )
            link = next(
                (e for e in after_exts if e.get("slug") == "link"),
                {},
            )
            cfg = dict(link.get("config") or {}) if isinstance(link, dict) else {}

            def _cfg_val(d: dict[str, Any], key: str) -> Any:
                return d.get(key)

            def _same(a: Any, b: Any) -> bool:
                if isinstance(a, bool) or isinstance(b, bool):
                    return bool(a) == bool(b)
                try:
                    return int(a or 0) == int(b or 0)
                except (TypeError, ValueError):
                    return a == b

            applied_ok = all(
                _same(_cfg_val(cfg, k), v) for k, v in updates.items()
            )
            changed = any(
                not _same(_cfg_val(before_cfg, k), _cfg_val(cfg, k))
                for k in updates
            )
            after = summarize_lock(await refresh_lock(chaster, lock))
            if not applied_ok:
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=after,
                    facts=(
                        "Share links config did NOT take on Chaster "
                        f"(wanted {updates}, still "
                        f"+{cfg.get('timeToAdd')}s / -{cfg.get('timeToRemove')}s, "
                        f"nbVisits={cfg.get('nbVisits')}). "
                        "Lock may block extension edits, or values were rejected."
                    ),
                )
            if not changed:
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=after,
                    facts=(
                        "Share links already at that config "
                        f"(+{cfg.get('timeToAdd')}s / -{cfg.get('timeToRemove')}s, "
                        f"nbVisits={cfg.get('nbVisits')}) - nothing to update."
                    ),
                )
            return ChasterActionResult(
                ok=True,
                facts=(
                    f"CHASTER ACTION DONE (share links config):\n"
                    f"- Requested by: {requested_by}\n"
                    f"- Before: +{before_cfg.get('timeToAdd')}s / "
                    f"-{before_cfg.get('timeToRemove')}s · "
                    f"nbVisits={before_cfg.get('nbVisits')}\n"
                    f"- After: +{cfg.get('timeToAdd')}s / "
                    f"-{cfg.get('timeToRemove')}s · "
                    f"enableRandom={cfg.get('enableRandom')} · "
                    f"nbVisits={cfg.get('nbVisits')} "
                    f"(minimum visits before unlock) · "
                    f"loggedOnly={cfg.get('limitToLoggedUsers')}\n"
                    "Share URL stays in the Chaster UI — bot changes +/- and visit gate.\n"
                    f"{_status_lines('AFTER', after)}"
                ),
                lock=after,
                before=before,
            )

        if intent.kind == "configure_extension":
            lock_id = str(before.get("lock_id") or "")
            slug = (intent.title or "").strip()
            if not slug:
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=before,
                    facts="No extension slug for configure_extension.",
                )
            updates = _torment_config_for(slug, intent.reason or "", intent)
            if not updates:
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=before,
                    facts=f"No config updates computed for `{slug}`.",
                )
            try:
                before_exts = await chaster.list_lock_extensions(lock_id)
            except Exception as exc:  # noqa: BLE001
                return ChasterActionResult(
                    ok=False,
                    error=str(exc),
                    before=before,
                    lock=before,
                    facts=f"Could not read extensions: {exc}",
                )
            if not any(str(e.get("slug") or "") == slug for e in before_exts):
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=before,
                    facts=(
                        f"`{slug}` is not on the lock. "
                        f'Say: "activate {slug}" first (free tier max 3).'
                    ),
                )
            try:
                after_exts = await chaster.update_extension_config(
                    lock_id, slug, updates
                )
            except Exception as exc:  # noqa: BLE001
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=before,
                    facts=f"Could not configure `{slug}`: {exc}",
                )
            after_cfg = next(
                (
                    dict(e.get("config") or {})
                    for e in after_exts
                    if str(e.get("slug") or "") == slug
                ),
                {},
            )
            after = summarize_lock(await refresh_lock(chaster, lock))
            return ChasterActionResult(
                ok=True,
                facts=(
                    f"CHASTER ACTION DONE (`{slug}` config torment):\n"
                    f"- Requested by: {requested_by}\n"
                    f"- Applied: {json_dumps_safe(updates)}\n"
                    f"- Live now: {json_dumps_safe(after_cfg)[:500]}\n"
                    f"{_status_lines('AFTER', after)}"
                ),
                lock=after,
                before=before,
            )

        block = preflight_block_reason(intent, before)
        if block:
            facts = (
                f"CHASTER ACTION BLOCKED:\n"
                f"- Requested by: {requested_by}\n"
                f"- Requested action: {intent.kind}\n"
                f"- Reason: {block}\n"
                f"{_status_lines('CURRENT LOCK STATUS', before)}\n"
                "Tell the requester what the current status is and that nothing was changed."
            )
            return ChasterActionResult(
                ok=True,
                facts=facts,
                lock=before,
                before=before,
                blocked=True,
            )

        if intent.kind == "add_time":
            secs = int(intent.seconds or 0)
            try:
                from app.runtime_controls import get_controls

                hi = int(get_controls().max_add_time_seconds or 86400)
            except Exception:  # noqa: BLE001
                hi = 86400
            # Cap runaway LLM amounts to session maximum; never invent bigger adds
            if secs > hi:
                log.info("Clamped add_time %s → max %s", secs, hi)
                secs = hi
            if secs < -hi:
                log.info("Clamped remove_time %s → -max %s", secs, hi)
                secs = -hi
            intent = ChasterIntent(kind="add_time", seconds=secs, reason=intent.reason)
            await chaster.update_time(lock_id, secs)
            after = summarize_lock(await refresh_lock(chaster, lock))
            sign = "+" if secs >= 0 else ""
            return ChasterActionResult(
                ok=True,
                facts=_facts_after(
                    action_line=(
                        f"Changed timer by {sign}{format_duration(secs)} "
                        f"({secs} seconds)."
                    ),
                    before=before,
                    after=after,
                    requested_by=requested_by,
                ),
                lock=after,
                before=before,
            )

        if intent.kind == "freeze":
            await chaster.set_freeze(lock_id, True)
            after = summarize_lock(await refresh_lock(chaster, lock))
            return ChasterActionResult(
                ok=True,
                facts=_facts_after(
                    action_line="Froze the lock.",
                    before=before,
                    after=after,
                    requested_by=requested_by,
                ),
                lock=after,
                before=before,
            )

        if intent.kind == "unfreeze":
            await chaster.set_freeze(lock_id, False)
            after = summarize_lock(await refresh_lock(chaster, lock))
            try:
                from app.lockbox_sync import sync_duration_from_chaster
                from app.rad_lockbox import get_rad_client

                rad = get_rad_client()
                if rad is not None:
                    await sync_duration_from_chaster(
                        rad, chaster, reason="unfreeze_api", force=True
                    )
            except Exception:  # noqa: BLE001
                log.exception("R+D resync after unfreeze failed")
            return ChasterActionResult(
                ok=True,
                facts=_facts_after(
                    action_line="Unfroze the lock.",
                    before=before,
                    after=after,
                    requested_by=requested_by,
                ),
                lock=after,
                before=before,
            )

        if intent.kind == "toggle_freeze":
            await chaster.session_action("toggle_freeze", lock_id=lock_id)
            after = summarize_lock(await refresh_lock(chaster, lock))
            return ChasterActionResult(
                ok=True,
                facts=_facts_after(
                    action_line="Toggled freeze.",
                    before=before,
                    after=after,
                    requested_by=requested_by,
                ),
                lock=after,
                before=before,
            )

        if intent.kind == "hide_time":
            await chaster.set_display_remaining_time(lock_id, False)
            after = summarize_lock(await refresh_lock(chaster, lock))
            return ChasterActionResult(
                ok=True,
                facts=_facts_after(
                    action_line="Hid remaining time from wearer.",
                    before=before,
                    after=after,
                    requested_by=requested_by,
                ),
                lock=after,
                before=before,
            )

        if intent.kind == "show_time":
            await chaster.set_display_remaining_time(lock_id, True)
            after = summarize_lock(await refresh_lock(chaster, lock))
            try:
                from app.lockbox_sync import sync_duration_from_chaster
                from app.rad_lockbox import get_rad_client

                rad = get_rad_client()
                if rad is not None:
                    await sync_duration_from_chaster(
                        rad, chaster, reason="timer_revealed_api", force=True
                    )
            except Exception:  # noqa: BLE001
                log.exception("R+D resync after show_time failed")
            return ChasterActionResult(
                ok=True,
                facts=_facts_after(
                    action_line="Showed remaining time to wearer.",
                    before=before,
                    after=after,
                    requested_by=requested_by,
                ),
                lock=after,
                before=before,
            )

        if intent.kind == "pillory":
            # Real levers: duration = public voting window; timeToAdd = per community vote.
            secs = max(300, min(86400, int(intent.seconds or 300)))
            reason = (intent.reason or "AI Domme punishment").strip()[:500]
            time_to_add = max(
                60,
                min(
                    86400,
                    int(intent.time_to_add or DEFAULT_PILLORY_TIME_TO_ADD),
                ),
            )
            pillory_cfg = {
                "timeToAdd": time_to_add,
                # Anyone can pile on — more torment than logged-in-only default.
                "limitToLoggedUsers": False,
            }
            parked_note = ""
            try:
                ensured = await chaster.ensure_extension(
                    lock_id,
                    "pillory",
                    config=pillory_cfg,
                    park_if_needed=True,
                )
                parked = list(ensured.get("parked") or [])
                if parked:
                    names = ", ".join(
                        str(p.get("slug") or "?") for p in parked
                    )
                    parked_note = (
                        f" Temporarily parked `{names}` to free a slot "
                        f"(free tier max 3 extensions; duo-domme kept). "
                        'Say "restore parked extensions" later.'
                    )
                try:
                    await chaster.update_extension_config(
                        lock_id, "pillory", pillory_cfg
                    )
                except Exception:  # noqa: BLE001
                    pass
            except Exception as exc:  # noqa: BLE001
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=before,
                    facts=(
                        f"Could not enable Pillory on the lock: {exc}. "
                        "Free accounts are limited to 3 extensions — "
                        "park/remove one in Chaster, or use Plus, then retry."
                    ),
                )
            # Confirm pillory slug is actually present before claiming
            try:
                exts = await chaster.list_lock_extensions(lock_id)
            except Exception as exc:  # noqa: BLE001
                return ChasterActionResult(
                    ok=False,
                    error=str(exc),
                    before=before,
                    lock=before,
                    facts=f"Could not verify extensions after pillory enable: {exc}",
                )
            live_pillory = next(
                (e for e in exts if str(e.get("slug") or "") == "pillory"),
                None,
            )
            if not live_pillory:
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=before,
                    facts=(
                        "Pillory is still not on the lock after activate — "
                        "not claiming a pillory. Check extension slots / Plus."
                    ),
                )
            live_tta = int((live_pillory.get("config") or {}).get("timeToAdd") or 0)
            try:
                await chaster.pillory(
                    lock_id,
                    duration_seconds=secs,
                    reason=reason,
                )
            except Exception as exc:  # noqa: BLE001
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=before,
                    facts=(
                        f"Pillory extension is on the lock but start failed: {exc}. "
                        "Nothing claimed."
                    ),
                )
            after = summarize_lock(await refresh_lock(chaster, lock))
            return ChasterActionResult(
                ok=True,
                facts=_facts_after(
                    action_line=(
                        f"Pilloried for {format_duration(secs)} "
                        f"(public Activity feed window). "
                        f"Each community vote adds "
                        f"{format_duration(live_tta or time_to_add)} "
                        f"(pillory timeToAdd; anyone may vote). "
                        f"Reason shown: {reason}.{parked_note}"
                    ),
                    before=before,
                    after=after,
                    requested_by=requested_by,
                ),
                lock=after,
                before=before,
            )

        if intent.kind == "set_note":
            content = (intent.reason or "").strip()
            if not content:
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=before,
                    facts=(
                        f"CHASTER ACTION BLOCKED:\n- Requested by: {requested_by}\n"
                        "- Reason: note text missing.\n"
                        "Ask Domme for the exact note text."
                    ),
                )
            try:
                await chaster.set_keyholder_note(lock_id, content)
                after = summarize_lock(await refresh_lock(chaster, lock))
                return ChasterActionResult(
                    ok=True,
                    facts=_facts_after(
                        action_line=f"Set keyholder note: {content[:200]}",
                        before=before,
                        after=after,
                        requested_by=requested_by,
                    ),
                    lock=after,
                    before=before,
                )
            except Exception as note_exc:  # noqa: BLE001
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=before,
                    facts=(
                        f"CHASTER ACTION BLOCKED:\n- Requested by: {requested_by}\n"
                        f"- Tried to set keyholder note but failed: {note_exc}\n"
                        "(Notes need Chaster Plus on the keyholder account.)\n"
                        f"{_status_lines('CURRENT LOCK STATUS', before)}\n"
                        "Do NOT claim the note was saved."
                    ),
                )

        if intent.kind == "history_message":
            body = (intent.reason or "").strip()
            title = (intent.title or "").strip() or "Message from your keyholders"
            if not body:
                return ChasterActionResult(
                    ok=True,
                    blocked=True,
                    before=before,
                    lock=before,
                    facts=(
                        f"CHASTER ACTION BLOCKED:\n- Requested by: {requested_by}\n"
                        "- Reason: message text missing.\n"
                        'Say: message him: Title | your text  '
                        'or: send him a lock message: be good tonight'
                    ),
                )
            await chaster.post_custom_log(
                title=title,
                description=body,
                role="keyholder",
                lock_id=lock_id,
            )
            after = summarize_lock(await refresh_lock(chaster, lock))
            return ChasterActionResult(
                ok=True,
                facts=_facts_after(
                    action_line=(
                        f"Posted lock history message (push): [{title}] {body[:240]}"
                    ),
                    before=before,
                    after=after,
                    requested_by=requested_by,
                ),
                lock=after,
                before=before,
            )

        if intent.kind == "apply_planned":
            return await _run_apply_planned(
                chaster,
                lock=lock,
                before=before,
                lock_id=lock_id,
                context=intent.reason or "",
                requested_by=requested_by,
            )

        if intent.kind in ("unsupported_reminders", "unsupported_notifications"):
            label = (
                "reminder notifications"
                if intent.kind == "unsupported_reminders"
                else "custom notification messages"
            )
            return ChasterActionResult(
                ok=True,
                blocked=True,
                before=before,
                lock=before,
                facts=(
                    f"CHASTER ACTION BLOCKED (API source of truth):\n"
                    f"- Requested by: {requested_by}\n"
                    f"- Feature: {label}\n"
                    "- Result: NOT AVAILABLE. Chaster's public API cannot set "
                    "wearer reminder schedule or custom push notification text.\n"
                    f"{_status_lines('CURRENT LOCK STATUS', before)}\n"
                    "Tell Domme this honestly. Do NOT claim it was changed."
                ),
            )

        if intent.kind == "tour_step":
            return ChasterActionResult(
                ok=False,
                facts="",
                error="tour_step must be run via run_tour_step()",
                before=before,
            )

        return ChasterActionResult(
            ok=False,
            facts="",
            error=f"Unhandled intent: {intent.kind}",
            before=before,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Chaster action failed")
        return ChasterActionResult(ok=False, facts="", error=str(exc))


def _extract_quoted_note(context: str) -> str:
    for pattern in (
        r"[\"']([^\"']{8,500})[\"']",
        r"note[:\s]+[\"']?(.+?)(?:[\"']\s*$|$)",
        r"custom notification message[.\s]+[\"']?(.+?)(?:[\"']|$)",
    ):
        m = re.search(pattern, context or "", re.I | re.M)
        if m:
            return m.group(1).strip()
    return ""


def _domme_lock_snapshot(summary: dict[str, Any]) -> str:
    rem = summary.get("remaining") or "?"
    frozen = "frozen" if summary.get("is_frozen") else "not frozen"
    visible = (
        "timer visible to him"
        if summary.get("display_remaining_time")
        else "timer hidden from him"
    )
    wearer = summary.get("username") or "him"
    return (
        f"Right now on {wearer}: {rem} left, {frozen}, {visible}."
    )


def _activation_followup(slug: str) -> str:
    s = (slug or "").lower()
    tips = {
        "link": (
            "Share links are now on the lock. Configure with "
            '"set share links add 2 hours remove 5 minutes with 10 visits". '
            "The wearer shares the Chaster link UI — this bot cannot mint a new URL."
        ),
        "pillory": (
            "Pillory is on the lock. Start with "
            '"pillory him for 15 minutes, 10 minutes per vote because brat". '
            "timeToAdd = seconds each community vote adds; duration = voting window."
        ),
        "dice": (
            'Dice is ready. Harden with "configure dice stakes 2 hours", '
            "then order him to roll in Chaster."
        ),
        "wheel-of-fortune": (
            'Wheel is ready. Say "harden the wheel" to load cruel segments, '
            "then order spins in Chaster."
        ),
        "random-events": (
            'Random events ready. Say "configure random events hard".'
        ),
        "temporary-opening": (
            "Chaster hygiene plugin stays off. Use Request hygiene in this chat."
        ),
        "verification-picture": (
            'Verification picture is ready. Domme can say: '
            '"request verification picture".'
        ),
        "tasks": (
            'Tasks is ready. Domme can say: "assign task: edge for 5 minutes".'
        ),
        "jigsaw-puzzle": (
            "Jigsaw is on the lock. He plays puzzles in Chaster; "
            "we do not remotely move pieces."
        ),
    }
    return tips.get(s, "Duo Domme still controls time/freeze/timer.")


def _describe_extension_control(slug: str, config: dict[str, Any]) -> list[str]:
    """Honest remote-control matrix for a plugin currently on the lock (from API)."""
    s = (slug or "").lower()
    lines: list[str] = []
    if s == "duo-domme":
        lines.append(
            "CONTROL: FULL via this bot — "
            + ", ".join(DUO_DOMME_ACTIONS)
            + "; plus lock history / push messages."
        )
        lines.append(
            'Say: "add 2 hours", "hide the timer", "freeze him", '
            '"message him: stay denied", '
            '"pillory him for 15 minutes, 10 minutes per vote".'
        )
        return lines
    if s == "link":
        lines.append(
            "CONTROL (Share links): CONFIG via this bot — timeToAdd / timeToRemove / "
            "enableRandom / nbVisits (minimum visits before unlock) / "
            "limitToLoggedUsers / visibleOnProfile. "
            "NO API to mint the public share URL (Chaster UI only)."
        )
        lines.append(
            f"Live config: +{config.get('timeToAdd')}s / -{config.get('timeToRemove')}s "
            f"per visit, enableRandom={config.get('enableRandom')}, "
            f"nbVisits={config.get('nbVisits')} (min visits gate), "
            f"limitToLoggedUsers={config.get('limitToLoggedUsers')}."
        )
        lines.append(
            'Say: "set share links add 2 hours remove 5 minutes with 10 visits". '
            "Order him to post the link; community clicks stack time."
        )
        return lines
    if s == "temporary-opening":
        lines.append(
            "CONTROL (Hygiene opening): BLOCKED — do not use this plugin. "
            "Lockee Request hygiene here; keyholder approves; Unlock / Relock the box."
        )
        return lines
    if s == "verification-picture":
        lines.append(
            "CONTROL: YES via API — request a verification picture "
            "(partner session + keyholder endpoint)."
        )
        lines.append(
            f"Live config: visibility={config.get('visibility')}, "
            f"peerVerification={config.get('peerVerification')}."
        )
        lines.append('Say: "request verification picture".')
        return lines
    if s == "tasks":
        lines.append(
            "CONTROL: YES via API when Tasks is on the lock — "
            "assign / start-timer / complete (partner session)."
        )
        lines.append(
            f"Live config: voteEnabled={config.get('voteEnabled')}, "
            f"enablePoints={config.get('enablePoints')}, "
            f"pointsRequired={config.get('pointsRequired')}."
        )
        lines.append('Say: "assign task: edge twice and wait".')
        return lines
    if s in ("jigsaw-puzzle", "jigsaw", "jigsaw-puzzles"):
        pieces = config.get("pieces")
        punish = config.get("punishments") or []
        puzzles = config.get("puzzles") or []
        open_n = sum(
            1
            for p in puzzles
            if isinstance(p, dict) and not p.get("completed")
        )
        lines.append(
            "CONTROL: ACTIVATE/CONFIG only. NOT remotely playable — "
            "extension action API returns Plugin not found for jigsaw."
        )
        lines.append(
            f"Live config: pieces={pieces}, open puzzles~{open_n}, "
            f"punishments={punish or 'none'}."
        )
        lines.append(
            "He solves puzzles in Chaster; failures/completions hit history; "
            "I react. I do not move pieces."
        )
        return lines
    if s == "dice":
        lines.append(
            "CONTROL: CONFIG multiplier/nbSides via this bot; he rolls in Chaster UI "
            "(no remote-roll API). Higher multiplier = nastier pip swings."
        )
        lines.append(
            f"Live config: multiplier={config.get('multiplier')}s per pip, "
            f"sides={config.get('nbSides')}."
        )
        lines.append('Say: "configure dice stakes 2 hours" then order him to roll.')
        return lines
    if s == "wheel-of-fortune":
        segs = config.get("segments") or []
        lines.append(
            "CONTROL: CONFIG segments via this bot (add/remove/freeze/pillory/text). "
            "He spins in Chaster — no remote-spin API."
        )
        lines.append(f"Live segments: {len(segs)} configured.")
        lines.append('Say: "harden the wheel" / "configure wheel of fortune".')
        return lines
    if s == "pillory":
        lines.append(
            "CONTROL: CONFIG timeToAdd (seconds EACH community vote adds) + "
            "limitToLoggedUsers; START via Duo Domme with duration (voting window) "
            "+ public reason. There is no votes-required field on pillory — "
            "share links nbVisits is the min-visits gate."
        )
        lines.append(
            f"Live config: timeToAdd={config.get('timeToAdd')}s per vote, "
            f"limitToLoggedUsers={config.get('limitToLoggedUsers')}."
        )
        lines.append(
            'Say: "pillory him for 15 minutes, 10 minutes per vote because brat".'
        )
        return lines
    if s == "random-events":
        lines.append(
            "CONTROL: CONFIG difficulty (easy/normal/hard/expert). "
            "Events fire inside Chaster; I react from history."
        )
        lines.append(f"Live config: difficulty={config.get('difficulty')}.")
        lines.append('Say: "configure random events hard".')
        return lines
    if s == "guess-timer":
        lines.append(
            "CONTROL: CONFIG min/max random penalty on wrong guess; "
            "pair with hide timer from Duo Domme."
        )
        lines.append(
            f"Live config: minRandomTime={config.get('minRandomTime')}, "
            f"maxRandomTime={config.get('maxRandomTime')}."
        )
        return lines
    lines.append(
        "CONTROL: Partner/third-party plugin — activate/config if trusted; "
        "no guaranteed remote actions. History reactions only unless documented."
    )
    return lines


def format_extensions_facts(
    summary: dict[str, Any],
    exts: list[dict[str, Any]],
    *,
    requested_by: str,
) -> str:
    lines = [
        "CHASTER EXTENSIONS (real API — do not invent controls):",
        f"- Requested by: {requested_by}",
        _domme_lock_snapshot(summary),
        "",
        "On his lock right now:",
    ]
    if not exts:
        lines.append("(none)")
    for ext in exts:
        slug = str(ext.get("slug") or "?")
        name = str(ext.get("display_name") or slug)
        mode = ext.get("mode") or ""
        cfg = ext.get("config") if isinstance(ext.get("config"), dict) else {}
        lines.append(f"• {name} (`{slug}`)" + (f" mode={mode}" if mode else ""))
        lines.extend(f"  - {bit}" for bit in _describe_extension_control(slug, cfg))
    lines.extend(
        [
            "",
            "API CAPABILITY MATRIX (verified against Chaster OpenAPI + live probes):",
            f"- Duo Domme session actions: {', '.join(DUO_DOMME_ACTIONS)} + custom history messages.",
            "- Hygiene: Chaster `temporary-opening` is blocked. "
            "Use Request hygiene + R+D box Unlock/Relock.",
            "- Verification picture: request when `verification-picture` is on the lock.",
            "- Tasks: assign/start-timer/complete when `tasks` is on the lock.",
            "- Share links (`link`): configure timeToAdd/timeToRemove/nbVisits/"
            "enableRandom; NO API to mint the public URL (UI only).",
            "- Pillory: CONFIG timeToAdd (+ per community vote) + limitToLoggedUsers; "
            "START via Duo Domme (duration window + reason). No votes-required field.",
            "- Dice/Wheel/Random-events/Jigsaw/Guess-timer: CONFIG via bot; "
            "gameplay is wearer-driven in Chaster (no remote spin/roll).",
            "- Free tier max 3 extensions — bot may park another plugin "
            '(never duo-domme) to enable one; "restore parked extensions" later.',
            '- Activate: "activate share links/tasks/verification/pillory/'
            'dice/wheel/random events/jigsaw".',
            "- Never invent controls that are not listed above.",
        ]
    )
    return "\n".join(lines)


def capabilities_text(summary: dict[str, Any], *, requested_by: str) -> str:
    """Domme-facing menu of real lock controls only."""
    return "\n".join(
        [
            _domme_lock_snapshot(summary),
            "",
            "Here's what we can do to him on the lock, Mistress:",
            '• Add time — say: "add 2 hours to his lock" / "add that time"',
            '• Remove time — say: "remove 30 minutes from his lock"',
            '• Freeze — say: "freeze his lock"',
            '• Unfreeze — say: "unfreeze him"',
            '• Toggle freeze — say: "toggle freeze"',
            '• Hide the timer from him — say: "hide the timer"',
            '• Show the timer again — say: "show the timer"',
            '• Pillory him (only if Pillory is on the lock) — say: '
            '"pillory him for 15 minutes, 10 minutes per vote because teasing"',
            '• Message / push via lock history — say: '
            '"message him: Be good tonight" or '
            '"send him a lock message: Tease | Edge twice and wait"',
            '• Recent history — say: "show lock history"',
            '• Extensions on the lock — say: "what extensions are on his lock"',
            '• Activate plugins — "activate share links", '
            '"activate tasks", "activate verification picture", "activate jigsaw". '
            "Hygiene plugin is blocked — use Request hygiene in this chat.",
            '• Share links config — "set share links add 2 hours remove 5 minutes with 10 visits"',
            "• Hygiene — Request hygiene in this chat (Chaster plugin stays off)",
            '• Verification picture — "request verification picture"',
            '• Tasks — "assign task: edge twice" (needs tasks)',
            "",
            "Jigsaw/Wheel/Dice: activate/config + history reactions — no remote puzzle play. "
            "Share link URLs are minted in the Chaster UI only.",
            "",
            "Just give the order in those words and I'll carry it out for real.",
        ]
    )


def format_capabilities_reply(result: ChasterActionResult) -> str:
    facts = (result.facts or "").strip()
    # Keep API truth plain — Domme/Sub both see the same factual block
    return facts


def format_kink_profile(username: str, profile: dict[str, Any]) -> str:
    kinks = list(profile.get("kinks") or [])
    toys = list(profile.get("toys") or [])
    bio = str(profile.get("bio") or "").strip()

    love = [
        k
        for k in kinks
        if isinstance(k, dict) and str(k.get("rating") or "").lower() == "love"
    ]
    like = [
        k
        for k in kinks
        if isinstance(k, dict) and str(k.get("rating") or "").lower() == "like"
    ]
    curious = [
        k
        for k in kinks
        if isinstance(k, dict) and str(k.get("rating") or "").lower() == "curious"
    ]

    def _names(items: list[Any], limit: int = 20) -> str:
        names: list[str] = []
        for i in items:
            if isinstance(i, dict) and i.get("name"):
                names.append(str(i.get("name") or "").strip())
            elif isinstance(i, str) and i.strip():
                names.append(i.strip())
        names = [n for n in names if n]
        if not names:
            return "(none listed)"
        shown = names[:limit]
        extra = len(names) - len(shown)
        text = ", ".join(shown)
        if extra > 0:
            text += f" … +{extra} more"
        return text

    lines = [
        f"Here's what {username} has on their profile:",
    ]
    if bio:
        lines.append(f"Bio: {bio}")
    lines.append(f"Loves: {_names(love)}")
    lines.append(f"Likes: {_names(like)}")
    if curious:
        lines.append(f"Curious about: {_names(curious, 12)}")
    lines.append(f"Toys listed: {_names(toys, 24)}")
    lines.append(
        f"({len(kinks)} kinks, {len(toys)} toys on file — ask if you want a category sliced thinner.)"
    )
    return "\n".join(lines)


def format_truth_reply(
    *,
    requested_by: str,
    step_label: str,
    step_num: int,
    step_total: int,
    result: ChasterActionResult,
    more_remaining: bool,
) -> str:
    """In-character Domme-speak grounded only in verified lock changes."""
    after = result.lock or result.before or {}
    snap = _domme_lock_snapshot(after) if after else ""

    if not result.ok:
        return (
            f"Mistress, that didn't take. {step_label} failed. "
            "Nothing changed on him. Want me to try again?"
        )

    if result.blocked:
        # Soft refusal — still Domme-speak, no tech jargon
        reason = ""
        facts = result.facts or ""
        if "already frozen" in facts.lower():
            reason = "He's already frozen."
        elif "already unfrozen" in facts.lower():
            reason = "He's already unfrozen."
        elif "already hidden" in facts.lower():
            reason = "His timer is already hidden."
        elif "already visible" in facts.lower():
            reason = "His timer is already showing."
        elif "not locked" in facts.lower():
            reason = "There's no active lock to touch."
        elif "plus" in facts.lower() or "note" in facts.lower():
            reason = "I couldn't save a keyholder note on this account."
        elif "reminder" in facts.lower() or "notification" in facts.lower():
            reason = "I can't set reminder or custom notification texts on his lock."
        else:
            reason = "I couldn't make that change."
        out = f"Mistress — {reason} {snap}".strip()
        if more_remaining:
            out += ' Say "next" if you want the next one.'
        return out

    # Success — map step labels / kinds into cruel-playful confirmation
    label = (step_label or "").lower()
    if "hide" in label:
        action = "I've hidden the timer from him."
    elif "show" in label:
        action = "I've shown him the timer again."
    elif "unfreeze" in label:
        action = "I've unfrozen him — time is moving again."
    elif "toggle" in label and "freeze" in label:
        action = "I've toggled his freeze."
    elif "freeze" in label:
        action = "I've frozen him — the clock stops for him."
    elif "pillory" in label:
        action = "I've put him in the pillory."
    elif "history" in label or "message" in label or "push" in label:
        action = "I've posted a message to his lock history — he should get a push."
    elif "add" in label or "time" in label:
        action = "I've changed his lock time."
    elif "note" in label:
        action = "I've left a note on him."
    else:
        action = f"Done — {step_label}."

    # Prefer BEFORE/AFTER remaining if present in facts
    before_rem = after_rem = None
    before_frozen = after_frozen = None
    section = None
    for line in (result.facts or "").splitlines():
        if line.startswith("BEFORE"):
            section = "b"
        elif line.startswith("AFTER"):
            section = "a"
        elif line.startswith("- Remaining:"):
            val = line.split(":", 1)[-1].strip()
            if section == "b":
                before_rem = val
            elif section == "a":
                after_rem = val
        elif line.startswith("- Frozen:"):
            val = line.split(":", 1)[-1].strip().lower() == "true"
            if section == "b":
                before_frozen = val
            elif section == "a":
                after_frozen = val

    detail_bits: list[str] = []
    if before_rem and after_rem and before_rem != after_rem:
        detail_bits.append(f"Time went from {before_rem.split('(')[0].strip()} to {after_rem.split('(')[0].strip()}.")
    if before_frozen is not None and after_frozen is not None and before_frozen != after_frozen:
        detail_bits.append("Frozen." if after_frozen else "Unfrozen.")

    lines = [f"Mistress — {action}"]
    if detail_bits:
        lines.append(" ".join(detail_bits))
    if snap:
        lines.append(snap)
    if more_remaining:
        lines.append('Say "next" for the next one.')
    elif step_total > 1:
        lines.append("That's all of them for now.")
    return "\n".join(lines)


async def run_tour_step(
    chaster: ChasterClient,
    step: dict[str, Any],
    *,
    requested_by: str,
) -> ChasterActionResult:
    kind = str(step.get("kind") or "")
    if kind == "set_note":
        intent = ChasterIntent(kind="set_note", reason=str(step.get("note") or ""))
    elif kind == "pillory":
        intent = ChasterIntent(
            kind="pillory",
            seconds=int(step.get("seconds") or 300),
            reason=str(step.get("reason") or "Mistress's order"),
            time_to_add=int(
                step.get("time_to_add")
                or step.get("timeToAdd")
                or DEFAULT_PILLORY_TIME_TO_ADD
            ),
        )
    elif kind in (
        "hide_time",
        "show_time",
        "freeze",
        "unfreeze",
        "toggle_freeze",
        "status",
        "unsupported_reminders",
        "unsupported_notifications",
    ):
        intent = ChasterIntent(kind=kind)  # type: ignore[arg-type]
    elif kind == "add_time":
        intent = ChasterIntent(kind="add_time", seconds=int(step.get("seconds") or 0))
    else:
        return ChasterActionResult(
            ok=True,
            blocked=True,
            facts=(
                f"CHASTER ACTION BLOCKED:\n- Unknown tour step kind '{kind}'.\n"
                "Do NOT claim anything changed."
            ),
        )
    return await run_chaster_intent(chaster, intent, requested_by=requested_by)


async def _run_apply_planned(
    chaster: ChasterClient,
    *,
    lock: dict[str, Any],
    before: dict[str, Any],
    lock_id: str,
    context: str,
    requested_by: str,
) -> ChasterActionResult:
    """Apply supported planned tweaks; honestly report unsupported ones."""
    ctx = (context or "").lower()
    lines = [
        "CHASTER APPLY-PLAN RESULT (real API — do not invent):",
        f"- Requested by: {requested_by}",
        _status_lines("BEFORE", before),
        "ACTIONS:",
    ]
    did_any = False

    wants_hide = bool(
        re.search(r"\b(visibility|hide|hidden|invisible|display.?remaining)\b", ctx)
    )
    wants_show = bool(re.search(r"\b(show|reveal|unhide)\b.*\b(time|timer|visibility)\b", ctx))
    wants_note = bool(re.search(r"\bnote\b", ctx))
    wants_notif = bool(
        re.search(r"\b(notif|reminder|notify|notification)\b", ctx)
    )

    if wants_hide and not wants_show:
        try:
            block = preflight_block_reason(ChasterIntent(kind="hide_time"), before)
            if block:
                lines.append(f"- hide timer: skipped ({block})")
            else:
                await chaster.set_display_remaining_time(lock_id, False)
                did_any = True
                lines.append("- hide timer: DONE (displayRemainingTime=false)")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"- hide timer: FAILED ({exc})")

    if wants_note:
        note = _extract_quoted_note(context)
        if not note:
            lines.append(
                "- keyholder note: NOT DONE (no note text found in recent plan). "
                "Ask Domme for the exact note."
            )
        else:
            try:
                await chaster.set_keyholder_note(lock_id, note)
                did_any = True
                lines.append(f"- keyholder note: DONE ({note[:120]})")
            except Exception as exc:  # noqa: BLE001
                lines.append(
                    f"- keyholder note: NOT AVAILABLE ({exc}). "
                    "Requires Chaster Plus on the keyholder account. Do NOT claim it was saved."
                )

    if wants_notif:
        lines.append(
            "- reminders / custom notifications: NOT AVAILABLE via Chaster public API. "
            "Do NOT claim notifications were changed."
        )

    if not (wants_hide or wants_show or wants_note or wants_notif):
        # Still try hide if Domme said "in turn" after a visibility plan with little context
        lines.append(
            "- No recognizable Chaster tweaks in recent plan text "
            "(supported: hide/show timer, keyholder note). "
            "Reminders/notifications cannot be set by API."
        )

    after = summarize_lock(await refresh_lock(chaster, lock))
    lines.append(_status_lines("AFTER", after))
    lines.append(
        "Only report DONE items as real. Clearly tell Domme what could not be applied."
    )
    return ChasterActionResult(
        ok=True,
        facts="\n".join(lines),
        lock=after,
        before=before,
        blocked=not did_any,
    )


_LOCK_TAG = re.compile(
    r"\[\[\[LOCK\]\]\]\s*(.*?)\s*\[\[\[/LOCK\]\]\]",
    re.I | re.S,
)


def _normalize_lock_body(body: str) -> str:
    """Models often write add_time <3900> — strip angle brackets around numbers."""
    text = (body or "").strip()
    text = re.sub(r"<\s*(-?\d+(?:\.\d+)?)\s*>", r"\1", text)
    text = text.replace("×", "x")
    return text.strip()


def parse_lock_tag_body(body: str) -> ChasterIntent | None:
    """Parse a single [[[LOCK]]] body into an intent (AI Domme self-grant)."""
    text = _normalize_lock_body(body)
    if not text:
        return None
    low = text.lower().strip()
    # History / push message: message Title | body   OR   message: body
    msg_m = re.match(
        r"^(?:message|history|notify|push)\s*(?::|\s+)\s*(.+)$",
        text,
        re.I | re.S,
    )
    if msg_m:
        payload = msg_m.group(1).strip()
        title = "Message from your keyholders"
        body_text = payload
        if "|" in payload:
            left, right = payload.split("|", 1)
            if left.strip() and right.strip():
                title, body_text = left.strip()[:200], right.strip()
        return ChasterIntent(
            kind="history_message",
            title=title,
            reason=body_text[:2000],
        )
    # show / hide timer
    if re.search(r"\b(show|unhide|reveal)\b", low) and re.search(
        r"\b(time|timer)\b", low
    ):
        return ChasterIntent(kind="show_time")
    if low in ("show_time", "unhide", "show"):
        return ChasterIntent(kind="show_time")
    if re.search(r"\b(hide|conceal)\b", low) and re.search(r"\b(time|timer)\b", low):
        return ChasterIntent(kind="hide_time")
    if low in ("hide_time", "hide"):
        return ChasterIntent(kind="hide_time")
    if low in ("unfreeze",) or re.search(r"\bunfreeze\b", low):
        return ChasterIntent(kind="unfreeze")
    if low in ("freeze",) or re.fullmatch(r"\s*freeze\s*", low):
        return ChasterIntent(kind="freeze")
    # add_time / remove_time with seconds or "10m" (optional <> already stripped)
    m = re.search(
        rf"\b(add_time|remove_time|add|remove)\s+(-?\d+(?:\.\d+)?)\s*({_TIME_UNIT})?\b",
        low,
    )
    if m:
        kind_raw, amount, unit = m.group(1), m.group(2), m.group(3)
        secs = _to_seconds(amount, unit or "s")
        if kind_raw.startswith("remove") or secs < 0:
            return ChasterIntent(kind="add_time", seconds=-abs(secs))
        return ChasterIntent(kind="add_time", seconds=abs(secs))
    m2 = re.search(rf"^(-?\d+(?:\.\d+)?)\s*({_TIME_UNIT})\s*$", low)
    if m2:
        secs = _to_seconds(m2.group(1), m2.group(2))
        return ChasterIntent(kind="add_time", seconds=secs)
    m3 = re.search(rf"\bpillory(?:\s+(\d+(?:\.\d+)?)\s*({_TIME_UNIT})?)?\b", low)
    if m3:
        if m3.group(1):
            secs = max(300, _to_seconds(m3.group(1), m3.group(2) or "s"))
        else:
            secs = 300
        return ChasterIntent(
            kind="pillory",
            seconds=secs,
            reason="AI Domme decision",
            time_to_add=_parse_pillory_time_to_add(low),
        )
    # Fall back to normal intent parser on the body alone
    return parse_chaster_intent(text)


def parse_lock_tag_bodies(body: str) -> list[ChasterIntent]:
    """Parse one LOCK tag that may contain multiple actions (· / ; / newlines)."""
    text = _normalize_lock_body(body)
    if not text:
        return []
    parts = [
        p.strip()
        for p in re.split(r"\s*[·•|;]\s*|\n+", text)
        if p and p.strip()
    ]
    if not parts:
        parts = [text]
    intents: list[ChasterIntent] = []
    for part in parts:
        intent = parse_lock_tag_body(part)
        if intent and intent.kind in MUTATING:
            intents.append(intent)
    if not intents:
        intent = parse_lock_tag_body(text)
        if intent and intent.kind in MUTATING:
            intents.append(intent)
    return intents


def extract_lock_commands(text: str) -> tuple[str, list[ChasterIntent]]:
    """Strip [[[LOCK]]]…[[[/LOCK]]] tags and return intents to execute."""
    intents: list[ChasterIntent] = []

    def _repl(match: re.Match[str]) -> str:
        intents.extend(parse_lock_tag_bodies(match.group(1)))
        return ""

    cleaned = _LOCK_TAG.sub(_repl, text or "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, intents


def format_group_lock_confirm(
    *,
    bot_name: str,
    domme_title: str,
    intent: ChasterIntent,
    result: ChasterActionResult,
) -> str:
    """Sub-facing confirmation after either Domme changes the lock."""
    title = (domme_title or "the Domme").strip() or "the Domme"
    if not result.ok or result.blocked:
        return ""
    kind = intent.kind
    if kind == "show_time":
        action = "I've shown you the timer"
    elif kind == "hide_time":
        action = "I've hidden the timer again"
    elif kind == "freeze":
        action = "I've frozen you"
    elif kind == "unfreeze":
        action = "I've unfrozen you — time moves again"
    elif kind == "add_time":
        mins = max(1, abs(int(intent.seconds)) // 60)
        if intent.seconds < 0:
            action = f"I've taken {mins} minutes off"
        else:
            action = f"I've added {mins} minutes"
    elif kind == "pillory":
        action = "I've put you in the pillory"
    elif kind == "history_message":
        action = "I've left a message on your lock"
    else:
        action = "I've changed your lock"
    rem = ""
    lock = result.lock or {}
    if isinstance(lock, dict) and lock.get("remaining"):
        rem = f" Remaining: {lock.get('remaining')}."
    return (
        f"{action}.{rem}\n"
        f"{title} and I decide your lock — remember that. — {bot_name}"
    )
