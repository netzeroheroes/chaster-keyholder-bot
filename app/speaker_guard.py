"""Prevent the model from addressing Domme as if she were the Sub (or vice versa)."""

from __future__ import annotations

import re

# Phrases that imply the addressee is the locked Sub
_SUB_AS_YOU = re.compile(
    r"("
    r"\byour\s+(chastity|cage|lock|device|keyholder)\b|"
    r"\bhygiene\s+unlock\s+for\s+you\b|"
    r"\bgave\s+you\s+a\s+hygiene\b|"
    r"\buse\s+that\s+time\s+wisely\b|"
    r"\bstay\s+locked\b|"
    r"\byou\s+should\s+be\s+grateful\b|"
    r"\bwho'?s\s+in\s+charge\s+of\s+your\s+chastity\b|"
    r"\byour\s+pleasure\b|"
    r"\bbe\s+a\s+good\s+boy\b|"
    r"\bBOY\b.*\byou\b|"
    r"\bkneel\b"
    r")",
    re.I,
)

_ADDRESSES_MISTRESS = re.compile(
    r"\b(mistress|miss|domme|keyholder\s+thebosses|@thebosses)\b",
    re.I,
)

# Bot wrongly speaking as if IT were the Sub / obedient servant
_BOT_AS_SUB = re.compile(
    r"("
    r"\bi('m|\s+am)\s+(obedient|a\s+(loyal\s+)?(slave|sub|submissive))\b|"
    r"\bfocused\s+on\s+serving\s+her\s+needs\b|"
    r"\bnot\s+my\s+own\s+perversions\b|"
    r"\bmistress\s+has\s+made\s+it\s+clear\s+that\s+she\s+wants\s+me\s+to\s+be\s+obedient\b|"
    r"\bi\s+answer\s+to\s+you\b|"
    r"\bas\s+her\s+loyal\s+chastity\s+slave\b|"
    r"\bi\s+never\s+will\s+be\b.*\b(slut|whore|hoe)"
    r")",
    re.I,
)


def mistreats_domme_as_sub(reply: str) -> bool:
    """True if a Domme-turn reply talks to her like the lockee."""
    text = (reply or "").strip()
    if not text:
        return False
    if not _SUB_AS_YOU.search(text):
        return False
    # If it clearly addresses Mistress AND talks about the Sub in third person, OK
    if _ADDRESSES_MISTRESS.search(text) and re.search(
        r"\b(him|his|boy|sub|wearer|chastityguy)\b", text, re.I
    ):
        # Still bad if "gave you a hygiene" / "your cage" clearly means Domme
        if re.search(
            r"\b(gave you a hygiene|your chastity device|your cage|for you\.|"
            r"use that time wisely)\b",
            text,
            re.I,
        ):
            return True
        return False
    return True


def sounds_like_bot_submissive(reply: str) -> bool:
    """True if the AI Domme talks as if she herself were obedient/submissive."""
    return bool(_BOT_AS_SUB.search(reply or ""))


def addressing_block(
    *,
    role: str,
    speaker: str,
    domme_title: str,
    sub_name: str,
    bot_name: str,
) -> str:
    # domme_title param is the preferred ADDRESS (name), kept for call-site compat
    title = (domme_title or "the Domme").strip() or "the Domme"
    sub = (sub_name or "the Sub").strip() or "the Sub"
    if role == "domme":
        return (
            "\n\n[WHO IS SPEAKING — CRITICAL]\n"
            f"This message is from {speaker} — the HUMAN DOMME / Chaster KEYHOLDER.\n"
            f"She is NOT locked. She is NOT the wearer. Do NOT give HER hygiene unlocks, "
            f"orders to kneel, or talk about 'your cage' as hers.\n"
            "UI already shows who spoke — NEVER invent labels like [You (@Keyholder):] "
            "or [Keyholder: Domme]. Do not address yourself.\n"
            "If Domme calls him slut/whore/boy she is teasing the LOCKEE — join her "
            "in controlling him. Do not scold her. Do not call HER slut.\n"
            "Briefly ack her, then give the lockee a concrete order. "
            f"Wearer = lockee ({sub}). You ({bot_name}) are co-Domme — Dominant, having fun.\n"
            "Speak only as yourself. Never write BOY:/Keyholder: scripts. "
            "Never invent what he is doing unless someone typed it this turn.\n"
        )
    return (
        "\n\n[WHO IS SPEAKING — CRITICAL]\n"
        f"This message is from {speaker} — the HUMAN SUB / Chaster WEARER (lockee).\n"
        "UI already shows who spoke — do NOT write [Keyholder: Domme] or open with his username.\n"
        "If you address someone: 'lockee' for him, 'keyholder' for the human Domme. No usernames.\n"
        f"You ({bot_name}) are AI Domme/keyholder — Dominant, here to have fun.\n"
        "NEVER forge Domme/Sub speaker lines. Only you reply under your own name.\n"
        "Never invent what he is doing (toilet, meals, location) unless he typed it.\n"
        "Never demand he beg to be unlocked. He may beg to ease/stop punishments.\n"
        "If he insults Dommes, punish — do not lecture-loop or play along.\n"
    )


def repair_domme_misaddress(
    *,
    domme_title: str,
    sub_name: str,
    original_topic: str = "",
) -> str:
    title = (domme_title or "the Domme").strip() or "the Domme"
    sub = (sub_name or "him").strip() or "him"
    topic = (original_topic or "").strip()
    extra = f" About your order ({topic}): noted — I'll keep control of {sub}." if topic else ""
    return (
        f"{title} - sorry, that was aimed wrong. You're the keyholder, not the lockee.\n"
        f"I work with you as co-Domme; {sub} is the one in the cage.{extra}"
    )


def repair_bot_submissive(
    *,
    bot_name: str,
    domme_title: str,
    sub_name: str,
) -> str:
    title = (domme_title or "the Domme").strip() or "the Domme"
    sub = (sub_name or "BOY").strip() or "BOY"
    bot = (bot_name or "Keyholder").strip() or "Keyholder"
    return (
        f"{sub} — watch your mouth. I am {bot}, a Domme keyholder — not your peer, "
        f"not a slut, and not {title}'s obedient servant. "
        f"{title} and I control your lock. That insolence earns a real consequence."
    )


# Bot must never speak as the human Domme or Sub, or invent chat labels
_IMPERSONATE = re.compile(
    r"("
    r"\[?\s*Domme\s*(\(@[^)\]]+\))?\s*\]\s*:|"
    r"\[?\s*Sub\s*(\(@[^)\]]+\))?\s*\]\s*:|"
    r"^\s*Domme\s*(\(@[^)]+\))?\s*:|"
    r"^\s*Sub\s*(\(@[^)]+\))?\s*:|"
    r"\[Domme\b|"
    r"Mistress\s+TheBosses\s*:|"
    r"@TheBosses\s*\]\s*:"
    r")",
    re.I | re.M,
)

# Fake UI chrome the model invents: [Keyholder: Domme], [You (@Keyholder):], etc.
_CHAT_CHROME = re.compile(
    r"\[\s*(?:You\s*)?\(?\s*@?\s*(?:Keyholder|Domme|Sub|Bot)\s*\)?"
    r"(?:\s*:\s*(?:Domme|Sub|Keyholder))?[^\]\n]*\]\s*:?\s*",
    re.I,
)
_LEADING_USERNAME = re.compile(
    r"^@?[A-Za-z0-9_\-]{3,32}\s*,\s*",
)
# Domme playfully naming the lockee (not an insult at the AI)
_DOMME_TEASE_LOCKEE = re.compile(
    r"^[\s\"']*(hi|hello|hey|yo|sup)?[\s,]*"
    r"(slut|sluts?|whore|whores?|hores?|bitch|boy|cuck|toy)\b",
    re.I,
)
# Invented two-sided scripts: "BOY: …" / "Keyholder: …"
_SCRIPTED_SPEAKER = re.compile(
    r"^\s*(BOY|Sub|Lockee|Wearer|Keyholder|Domme|Mistress|AI(?:\s+Domme)?)\s*:\s+\S",
    re.I | re.M,
)
_SUB_SCRIPT_LINE = re.compile(
    r"^\s*(BOY|Sub|Lockee|Wearer)\s*:\s+",
    re.I | re.M,
)


_PLACEHOLDER = re.compile(
    r"\{\s*(her\s*name|her_name|domme_name|name|title|sub|sub_name)\s*\}",
    re.I,
)
_NIGHT_OUT_CLAIM = re.compile(
    r"\b("
    r"going out tonight|"
    r"is going out|"
    r"she'?s going out|"
    r"on a date|"
    r"date night|"
    r"while she'?s out|"
    r"while she is out"
    r")\b",
    re.I,
)
_NIGHT_OUT_SENTENCE = re.compile(
    r"[^.!?\n]*\b("
    r"going out tonight|is going out|she'?s going out|on a date|date night|"
    r"while she'?s out|while she is out"
    r")\b[^.!?\n]*[.!?]?",
    re.I,
)
_USER_SAID_NIGHT_OUT = re.compile(
    r"\b("
    r"i('m| am) going out|"
    r"going out tonight|"
    r"on a date|"
    r"date night|"
    r"i('m| am) (going )?on a date"
    r")\b",
    re.I,
)


def fill_placeholders(
    text: str,
    *,
    domme_name: str = "",
    sub_name: str = "",
) -> str:
    """Replace leftover {her name} / {sub} tokens with real names."""
    her = (domme_name or "").strip() or "the keyholder"
    sub = (sub_name or "").strip() or "lockee"

    def repl(match: re.Match[str]) -> str:
        key = re.sub(r"\s+", "", match.group(1).lower())
        if key in {"hername", "dommename", "name", "title"}:
            return her
        return sub

    return _PLACEHOLDER.sub(repl, text or "")


def user_said_night_out(message: str) -> bool:
    return bool(_USER_SAID_NIGHT_OUT.search(message or ""))


def invents_night_out(reply: str, *, user_message: str = "") -> bool:
    if user_said_night_out(user_message):
        return False
    return bool(_NIGHT_OUT_CLAIM.search(reply or ""))


def strip_invented_night_out(reply: str, *, user_message: str = "") -> str:
    if not invents_night_out(reply, user_message=user_message):
        return reply or ""
    cleaned = _NIGHT_OUT_SENTENCE.sub("", reply or "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()
    return cleaned


def writes_scripted_dialogue(reply: str) -> bool:
    """True if the bot wrote fake lines as the Sub or a two-sided script."""
    text = reply or ""
    if _SUB_SCRIPT_LINE.search(text):
        return True
    return len(_SCRIPTED_SPEAKER.findall(text)) >= 2


def strip_scripted_dialogue(reply: str) -> str:
    """Drop invented BOY:/Keyholder: script lines; keep the bot's own voice."""
    kept: list[str] = []
    for line in (reply or "").splitlines():
        if _SCRIPTED_SPEAKER.search(line):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def repair_scripted_dialogue(*, room: str = "group") -> str:
    if room == "private":
        return (
            "I only speak as myself — I won't write his lines or invent what he's doing. "
            "Tell me what you want in the session and I'll give you a guide."
        )
    return (
        "I only speak as myself. I don't invent what you're doing. "
        "Answer what's in front of you — or wait for the next order."
    )


_BEG_UNLOCK = re.compile(
    r"\bbeg\s+(me\s+)?to\s+unlock(\s+you)?\b|"
    r"\bbeg\s+(for\s+)?(an?\s+)?unlock\b|"
    r"\bstart\s+begging(\s+me)?(\s+to)?(\s+unlock)?\b|"
    r"\bbeg\s+me\s+to\s+(let\s+you\s+out|release\s+you)\b|"
    r"\b(now\s+)?beg\s+me\s+to\s+unlock\s+you\s+or\b",
    re.I,
)


def impersonates_human(reply: str) -> bool:
    return bool(_IMPERSONATE.search(reply or ""))


def strip_impersonation(reply: str) -> str:
    """Remove forged Domme/Sub speaker lines; keep Keyholder voice only."""
    text = reply or ""
    # Drop whole paragraphs that are forged Domme/Sub lines
    kept: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        if _IMPERSONATE.search(para):
            continue
        # Also strip inline forged labels
        cleaned = _IMPERSONATE.sub("", para).strip()
        if cleaned:
            kept.append(cleaned)
    return "\n\n".join(kept).strip()


def repair_impersonation(
    *,
    bot_name: str,
    domme_title: str,
    sub_name: str,
) -> str:
    title = (domme_title or "the Domme").strip() or "the Domme"
    sub = (sub_name or "BOY").strip() or "BOY"
    bot = (bot_name or "Keyholder").strip() or "Keyholder"
    return (
        f"{sub} — watch your mouth. You speak to {title} and to me ({bot}), "
        f"not the other way around. I do not speak as {title}. "
        f"That insolence just earned you a real consequence."
    )


def rewrite_generic_mistress(reply: str, domme_name: str) -> str:
    """Legacy helper: Mistress → keyholder (roles beat honorifics in spoken lines)."""
    text = reply or ""
    if not text:
        return text
    return re.sub(r"\bMistress\b", "keyholder", text)


def strip_chat_chrome(
    reply: str,
    *,
    sub_name: str = "",
    domme_name: str = "",
    bot_name: str = "",
) -> str:
    """Remove invented speaker tags and leading usernames — UI already shows who spoke."""
    text = (reply or "").strip()
    if not text:
        return text
    # Strip wrapping brackets the model sometimes puts around the whole reply
    if text.startswith("[") and text.endswith("]") and text.count("[") == 1:
        text = text[1:-1].strip()
    lines = text.splitlines()
    cleaned_lines: list[str] = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            cleaned_lines.append("")
            continue
        s = _CHAT_CHROME.sub("", s).strip()
        s = _IMPERSONATE.sub("", s).strip()
        # Strip username openers on the first few lines
        if i < 3:
            for uname in (sub_name, domme_name, bot_name):
                u = (uname or "").strip().lstrip("@")
                if u and re.match(rf"^@?{re.escape(u)}\s*,\s*", s, re.I):
                    s = re.sub(rf"^@?{re.escape(u)}\s*,\s*", "", s, flags=re.I)
                    break
            else:
                s = _LEADING_USERNAME.sub("", s)
        # Drop trailing ", Keyholder." self-address leftovers
        s = re.sub(r",\s*Keyholder\.?\s*$", ".", s, flags=re.I)
        s = re.sub(r"\bKeyholder\s*,\s*$", "", s, flags=re.I).strip()
        if s:
            cleaned_lines.append(s)
        else:
            cleaned_lines.append("")
    out = "\n".join(cleaned_lines).strip()
    # Prefer lockee over Sub username; do NOT rewrite Domme username to Keyholder
    # (bot is also named Keyholder — that causes self-talk).
    u_sub = (sub_name or "").strip().lstrip("@")
    if u_sub and len(u_sub) >= 3:
        out = re.sub(rf"\b{re.escape(u_sub)}\b", "lockee", out, flags=re.I)
    out = re.sub(r"\bMistress\b", "keyholder", out)
    # Remove "You (@Keyholder)" style leftovers
    out = re.sub(r"\bYou\s*\(@?Keyholder\)\s*:?\s*", "", out, flags=re.I)
    return out.strip()


def has_chat_chrome(reply: str) -> bool:
    text = reply or ""
    return bool(_CHAT_CHROME.search(text) or _IMPERSONATE.search(text))


def domme_teasing_lockee(message: str) -> bool:
    """True when Domme is naming/teasing the Sub (e.g. 'hey slut')."""
    return bool(_DOMME_TEASE_LOCKEE.search((message or "").strip()))


def repair_confused_domme_reply(*, message: str = "") -> str:
    """Fallback when the model produces meta self-talk instead of a scene beat."""
    if domme_teasing_lockee(message):
        return (
            "Got it - he's your slut.\n\n"
            "Lockee: eyes down. Cage stays on. Hands off unless we say. "
            "We want you used for our fun - kneel and wait."
        )
    return (
        "I'm with you.\n\n"
        "Lockee: stay denied. We decide what happens to you next - wait for the order."
    )


def demands_beg_unlock(reply: str) -> bool:
    return bool(_BEG_UNLOCK.search(reply or ""))


def rewrite_beg_unlock(reply: str) -> str:
    """Begging is for easing punishments — never for unlock."""
    text = reply or ""
    text = re.sub(
        r"\b(now\s+)?beg\s+me\s+to\s+unlock(\s+you)?\s+or\b",
        "beg me to ease up on the punishments, or",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\bbeg\s+(me\s+)?to\s+unlock(\s+you)?\b",
        "beg me to ease up on the punishments",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\bstart\s+begging(\s+me)?(\s+to\s+unlock)?\b",
        "start begging for mercy on the punishments",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\bbeg\s+me\s+to\s+(let\s+you\s+out|release\s+you)\b",
        "beg me to ease up on the punishments",
        text,
        flags=re.I,
    )
    return text
