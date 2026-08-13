from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

@dataclass
class RuleBreak:
    reason: str
    seconds: int = 600
    freeze: bool = False
    hide_timer: bool = False
    strike: int = 1  # disobedience streak after this offense
    # Extension levers to try (share links, tasks, pillory, verification)
    use_extensions: bool = True


# Gendered / sexualized insults Sub must not aim at Dommes / AI keyholder
# (Domme teasing HIM is role=domme and never hits these)
_SLUR = (
    r"sluts?|whores?|hores?|hoes?|bitches|bitch|biatch|bytch|"
    r"cunts?|thots?|skanks?|tramps?|hookers?|harlots?|"
    r"slags?|tarts?|wenches?"
)
_SLUR_OR_ANIMAL = _SLUR + r"|cow|pigs?|dogs?"
_SLUR_ADJ = r"(?:stupid|dumb|ugly|nasty|dirty|dumbass|fucking|lil'|little)\s+"

_HARD_PATTERNS: list[tuple[re.Pattern[str], RuleBreak]] = [
    (
        re.compile(
            r"\b(i\s+(came|orgasmed|finished)|came\s+without|ruined\s+without|"
            r"unlocked|took\s+(it|the cage)\s+off|removed\s+(my|the)\s+(cage|lock))\b",
            re.I,
        ),
        RuleBreak(reason="came/unlocked without permission", seconds=3600, freeze=True),
    ),
    # Slurs / insolent naming of Dommes or keyholder
    (
        re.compile(
            rf"^[\s\"']*(hi|hello|hey|yo|sup|hiya)?[\s,]*"
            rf"({_SLUR_ADJ})?({_SLUR})\b"
            rf"|^({_SLUR_ADJ})?({_SLUR})\s*[.!]?\s*$"
            rf"|\b(fuck you|fuck off|fuck u|\bfu\b|gtfo|stfu|shut up|shut it)\b"
            rf"|\b(you('re| are| r)\s+(a\s+)?({_SLUR_ADJ})?({_SLUR_OR_ANIMAL}))\b"
            rf"|\b(you are one of them)\b"
            rf"|\b(a\s+couple\s+of|couple\s+of|those|these|you\s+two|you\s+girls|"
            rf"both of you|you both)\s+({_SLUR_ADJ})?({_SLUR})\b"
            rf"|\b(hey|hi|hello|yo)\s+(you\s+)?({_SLUR_ADJ})?({_SLUR})\b"
            rf"|\b(call(ing)?\s+(you|her|them)\s+({_SLUR}))\b"
            rf"|\b(dumbass|idiot|moron|loser|bitchass)\b",
            re.I,
        ),
        RuleBreak(
            reason="disrespected Domme/keyholder (slur / insolent address)",
            seconds=1800,
            hide_timer=True,
        ),
    ),
    # Bratting / topping / sarcasm / refusal
    (
        re.compile(
            r"("
            r"^(whatever|yeah\s*yeah|sure\s*whatever|nah|meh|k+|kk|lol|lmao|lmfao|"
            r"idc|idgaf|ngl|bruh|ok\s*whatever|nope|as\s+if|pass|next|"
            r"bored|boring|try\s+me|prove\s+it|you\s+wish|too\s+bad|"
            r"deal\s+with\s+it|and\s+if\s+i\s+don'?t|or\s+what|so\s+what|"
            r"make\s+me|not\s+happening|not\s+listening|don'?t\s+care|"
            r"i\s+don'?t\s+care|who\s+cares|big\s+deal|sure\s+jan|"
            r"eye\s*roll|rolls?\s+eyes?|\*rolls?\s+eyes?\*)\s*[.!]?\s*$"
            r"|^no\s*[.!]?\s*$"
            r"|^h+m+\s*[.!]?\s*$"
            r"|\b(i\s+won'?t|i\s+refuse|not\s+doing\s+(that|it|this)|"
            r"make\s+me|fuck\s+off|i\s+quit|stop\s+controlling\s+me|"
            r"you\s+can'?t\s+make\s+me|i'?m\s+not\s+(doing|listening|obeying)|"
            r"try\s+and\s+stop\s+me|over\s+my\s+dead\s+body|"
            r"not\s+my\s+(domme|mistress|keyholder)|you'?re\s+not\s+my)\b"
            r"|\b(i\s+decide|you\s+can'?t|you\s+don'?t\s+control|"
            r"unlock\s+me\s+now|let\s+me\s+out\s+now|"
            r"you\s+(should|need\s+to|have\s+to)\s+(let|unlock|release)|"
            r"why\s+don'?t\s+you\s+(just\s+)?(unlock|let\s+me)|"
            r"i'?m\s+the\s+boss|i\s+run\s+this|you\s+work\s+for\s+me)\b"
            r"|\b(lol\s+no|haha\s+no|lmao\s+no|yeah\s+right|"
            r"as\s+if\s+i'?d|in\s+your\s+dreams|nice\s+try|"
            r"that'?s\s+cute|adorable\s+try|keep\s+dreaming|"
            r"you\s+wish\s+(i|you)|good\s+luck\s+with\s+that)\b"
            r")",
            re.I,
        ),
        RuleBreak(reason="bratting / defiance", seconds=1200, freeze=True, hide_timer=True),
    ),
]

_SOFT_PATTERNS: list[tuple[re.Pattern[str], RuleBreak]] = [
    (
        re.compile(
            r"\b(i\s+forgot|didn'?t\s+(edge|stroke|listen|obey)|"
            r"skipped|too\s+late|couldn'?t\s+be\s+bothered)\b",
            re.I,
        ),
        RuleBreak(reason="failed / skipped an order", seconds=900),
    ),
    (
        re.compile(
            r"\b(that'?s\s+not\s+fair|i\s+deserve\s+release|"
            r"you\s+have\s+to\s+(let|show|unhide|unlock))\b",
            re.I,
        ),
        RuleBreak(reason="demanded mercy / entitlement", seconds=600, hide_timer=True),
    ),
]

# Pleas are allowed — Sub may beg for mercy (timer/time), not issue orders
_BEGGING = re.compile(
    r"\b("
    r"please|pls|plz|i\s+beg|begging|may\s+i|"
    r"can\s+(i|you)|could\s+you|would\s+you|will\s+you|"
    r"pretty\s+please|i'?m\s+begging|please\s+mistress|please\s+miss|"
    r"have\s+mercy|be\s+merciful|if\s+it\s+pleases\s+you|"
    r"i\s+know\s+i\s+don'?t\s+deserve|only\s+if\s+you\s+(want|allow|say)"
    r")\b",
    re.I,
)

_MERCY_TOPIC = re.compile(
    r"\b("
    r"unhide|show\s+(me\s+)?(the\s+)?timer|reveal\s+(the\s+)?timer|"
    r"see\s+(the\s+)?(time|timer)|make\s+(the\s+)?timer\s+visible|"
    r"take\s+(some\s+|a\s+little\s+)?time\s+off|remove\s+(some\s+|a\s+little\s+)?time|"
    r"reduce\s+(the\s+|my\s+)?time|less\s+time|shorter|"
    r"ease\s+up|go\s+easier|give\s+me\s+a\s+break|"
    r"unfreeze|thaw|let\s+(the\s+)?(clock|time)\s+(run|move)|"
    r"stop\s+(the\s+)?punish(?:ment|ing)|stop\s+punishing|"
    r"ease\s+(the\s+|up\s+on\s+)?punish(?:ment|ments|ing)|"
    r"no\s+more\s+(extra\s+)?time|forgive\s+me|"
    r"stop\s+adding\s+time|go\s+easy"
    r")\b",
    re.I,
)

# Imperative / entitled orders — not allowed from Sub
_DIRECT_ORDER = re.compile(
    r"\b("
    r"unhide\s+(the\s+)?timer\s+now|show\s+(me\s+)?(the\s+)?timer\s+now|"
    r"(do\s+it|just\s+do\s+it|you\s+(will|must|have\s+to))|"
    r"(unhide|show|reveal|remove|reduce|unfreeze|unlock)\s+(it|the\s+timer|my\s+timer|time)\s*(now|immediately)?|"
    r"(take|remove)\s+\d+\s*(min|minute|hour|hr|day)s?\s*(off|from)|"
    r"add\s+-\d+|subtract\s+\d+|"
    r"add\s+(some|more|a\s+little|a\s+bit|extra)?\s*time|"
    r"(give|put)\s+(me\s+)?(some|more|extra)\s+time"
    r")\b",
    re.I,
)


def is_mercy_plea(message: str) -> bool:
    """Polite begging about timer visibility / less time / unfreeze."""
    text = (message or "").strip()
    if not text:
        return False
    return bool(_BEGGING.search(text) and _MERCY_TOPIC.search(text))


def is_direct_lock_order(message: str) -> bool:
    """Sub trying to command a lock change (not a polite plea)."""
    text = (message or "").strip()
    if not text:
        return False
    if is_mercy_plea(text):
        return False
    return bool(_DIRECT_ORDER.search(text) or _MERCY_TOPIC.search(text))


def _normalize_variants(text: str) -> list[str]:
    """Variants so common obfuscations still match (sl0t, b!tch, $lut, etc.)."""
    base = (text or "").strip().lower()
    if not base:
        return []
    out: list[str] = [base]
    t = base
    for a, b in (("@", "a"), ("$", "s"), ("!", "i"), ("*", ""), ("3", "e"), ("4", "a"), ("5", "s")):
        t = t.replace(a, b)
    out.append(t)
    out.append(re.sub(r"(.)\1{2,}", r"\1\1", t))
    # digit lookalikes: 0 as o or u (sl0t), 1 as i or l
    out.append(t.replace("0", "o").replace("1", "i"))
    out.append(t.replace("0", "u").replace("1", "l"))
    # de-dupe, keep order
    seen: set[str] = set()
    uniq: list[str] = []
    for v in out:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def detect_rule_break(message: str, *, role: str) -> RuleBreak | None:
    """Sub-only: detect clear rule breaks that justify automatic detriment."""
    if role != "sub":
        return None
    raw = (message or "").strip()
    if not raw:
        return None
    # Mercy pleas are allowed — never auto-punish begging for timer/time
    if is_mercy_plea(raw):
        return None

    variants = _normalize_variants(raw)

    def _any_match(pattern: re.Pattern[str]) -> bool:
        return any(pattern.search(v) for v in variants)

    # Slurs + bratting + major confessions always punish (even wrapped in "please")
    for pattern, br in _HARD_PATTERNS:
        if _any_match(pattern):
            return br

    # Soft questions / obedience should not punish milder failures
    if any(
        re.search(
            r"\b(what about|may i|can i|please|sorry|i will|yes mistress|yes miss|"
            r"yes keyholder|i'?ll obey|i will obey)\b",
            v,
            re.I,
        )
        for v in variants
    ):
        return None

    for pattern, br in _SOFT_PATTERNS:
        if _any_match(pattern):
            return br
    # Direct lock orders (no begging) are a control challenge
    if any(is_direct_lock_order(v) for v in variants):
        return RuleBreak(
            reason="gave lock orders instead of begging",
            seconds=900,
            hide_timer=True,
        )
    return None


def looks_like_obedience(message: str) -> bool:
    """Genuine apology / compliance — may cool the streak (not a punish)."""
    text = (message or "").strip()
    if not text:
        return False
    if detect_rule_break(text, role="sub"):
        return False
    return bool(
        re.search(
            r"\b("
            r"sorry|i'?m sorry|forgive me|i apologize|"
            r"yes (keyholder|mistress|miss|ma'?am)|"
            r"i('?ll| will) (obey|behave|listen|do (it|that|better))|"
            r"please (ease|stop|forgive)|i'?ll be good"
            r")\b",
            text,
            re.I,
        )
    )


def get_disobey_streak(memory: Any) -> int:
    ch = getattr(memory, "chastity", None) or {}
    if not isinstance(ch, dict):
        return 0
    try:
        return max(0, int(ch.get("disobey_streak") or 0))
    except (TypeError, ValueError):
        return 0


def bump_disobey_streak(memory: Any) -> int:
    """Increment lasting disobedience counter; return new strike count (1+)."""
    n = get_disobey_streak(memory) + 1
    ch = dict(getattr(memory, "chastity", None) or {})
    ch["disobey_streak"] = str(n)
    ch["disobey_last"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    memory.update_fields(chastity=ch)
    return n


def cool_disobey_streak(memory: Any, *, reset: bool = False) -> int:
    """Reduce or clear streak when he begs properly / obeys."""
    cur = get_disobey_streak(memory)
    if cur <= 0:
        return 0
    nxt = 0 if reset else max(0, cur - 1)
    ch = dict(getattr(memory, "chastity", None) or {})
    if nxt:
        ch["disobey_streak"] = str(nxt)
    else:
        ch.pop("disobey_streak", None)
    ch["disobey_last"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    memory.update_fields(chastity=ch)
    return nxt


def escalate_rule_break(
    br: RuleBreak,
    strike: int,
    *,
    min_seconds: int | None = None,
    max_seconds: int | None = None,
) -> RuleBreak:
    """Scale time + extras as disobedience continues (strike is 1-based).

    Cap / floor come from Domme session settings (min/max add time), not a hardcode.
    """
    n = max(1, int(strike or 1))
    lo = max(60, int(min_seconds or 60))
    hi = max(lo, int(max_seconds or 86400))
    # 1→base, 2→1.5x, 3→2.25x … until session max
    mult = min(6.0, 1.5 ** (n - 1))
    seconds = max(lo, min(hi, int(br.seconds * mult)))
    freeze = br.freeze or n >= 2
    hide = br.hide_timer or n >= 1
    reason = br.reason
    if n >= 2:
        reason = f"{br.reason} (strike {n} - escalating)"
    return RuleBreak(
        reason=reason,
        seconds=seconds,
        freeze=freeze,
        hide_timer=hide,
        strike=n,
        use_extensions=br.use_extensions,
    )


def format_auto_punish_reply(
    *,
    bot_name: str,
    reason: str,
    results: list,
    seconds: int,
    applied: list[str],
    strike: int = 1,
) -> str:
    """Immediate Domme-speak to the Sub after real Chaster detriment."""
    done = [r for r in results if getattr(r, "ok", False) and not getattr(r, "blocked", False)]
    if not done or not applied:
        return ""

    mins = max(1, int(seconds) // 60)
    bits: list[str] = []
    if "add_time" in applied:
        bits.append(f"I've added {mins} minutes to your lock")
    if "freeze" in applied:
        bits.append("frozen you so the clock stops")
    if "hide_time" in applied:
        bits.append("hidden the timer from you")
    if "configure_share_links" in applied:
        bits.append("hardened your share links (bigger add, smaller remove)")
    if "assign_task" in applied:
        bits.append("assigned you a Chaster task")
    if "pillory" in applied:
        bits.append("put you in the pillory")
    if "request_verification" in applied:
        bits.append("demanded a verification picture")
    if not bits:
        bits.append("I've punished you on the lock")

    action = ", and ".join(bits)
    if action and action[0].islower():
        action = action[0].upper() + action[1:]

    snap = ""
    lock = getattr(done[-1], "lock", None) or {}
    rem = lock.get("remaining") if isinstance(lock, dict) else None
    if rem:
        snap = f" Remaining: {rem}."

    strike_n = max(1, int(strike or 1))
    escalate_line = ""
    if strike_n >= 2:
        escalate_line = (
            f"\nThat's strike {strike_n}. Keep mouthing off and it gets worse each time."
        )
    elif strike_n == 1:
        escalate_line = "\nKeep it up and the next hit will be harder."

    low_reason = (reason or "").lower()
    if "slur" in low_reason or "insolent" in low_reason or "disrespect" in low_reason:
        return (
            f"Watch your mouth. Slurs at Dommes or your keyholder earn real time.\n"
            f"{action}.{snap}{escalate_line}\n"
            f"Beg to ease the punishments - not for unlock. - {bot_name}"
        )
    if "brat" in low_reason or "defiance" in low_reason or "dismissive" in low_reason:
        return (
            f"{action} for bratting.{snap}{escalate_line}\n"
            f"Obey, or beg to ease the punishments. - {bot_name}"
        )
    return (
        f"{action} for {reason}.{snap}{escalate_line}\n"
        f"That's how this works, lockee — I control your lock. — {bot_name}"
    )
