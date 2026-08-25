"""Prevent the model from addressing Domme as if she were the Sub (or vice versa)."""

from __future__ import annotations

import re

# Hard: talking TO the keyholder as if SHE wears the cage
_SUB_AS_YOU = re.compile(
    r"("
    r"\bhygiene\s+unlock\s+for\s+you\b|"
    r"\bgave\s+you\s+a\s+hygiene\b|"
    r"\buse\s+that\s+time\s+wisely\b|"
    r"\bwho'?s\s+in\s+charge\s+of\s+your\s+chastity\b|"
    r"\byour\s+(chastity device|cage|lock|keyholder)\b"
    r")",
    re.I,
)
# Orders / vocatives aimed at the lockee while talking to the keyholder
_LOCKEE_ORDERS_ALWAYS = re.compile(
    r"("
    r"(?:,|\bnow,)\s*(?:sub|lockee|boy|wearer)\b|"
    r"\b(?:sub|lockee)\s*[.!]?\s*$|"
    r"\blean against the wall\b|"
    r"\bwatch the clock\b|"
    r"\bhands on (?:the|your) cage\b|"
    r"\beyes down\b|"
    r"i('ll| will) talk to her|"
    r"talk to her about what comes next|"
    r"\byou('re| are) (?:locked|denied|frozen|caged)\b|"
    r"\bshe(?:'ll| will) (?:just )?hand you\b|"
    r"\byou think she(?:'ll| will)\b|"
    r"\btell her how (?:badly )?you(?:'re| are) begging\b|"
    r"\bhand you freedom\b"
    r")",
    re.I,
)
# Lockee-tease aimed at whoever is listening — false-positives on a bull flirting with her
_LOCKEE_TEASE_TO_LISTENER = re.compile(
    r"("
    r"\bstay denied\b|"
    r"\bstay with that ache\b|"
    r"maybe if you earn it|"
    r"(?:^|[,.!?]\s+)pet\b|"
    r"\bpet[,.!?]"
    r"|"
    r"\bpatience,?\s+pet\b|"
    r"\byou(?:'ll| will) earn (?:your )?(?:release|freedom|unlock)\b|"
    r"\bthe cage waits\b|"
    r"\bespecially about her\b"
    r")",
    re.I,
)
_LOCKEE_ORDER_SENTENCE = re.compile(
    r"[^.!?\n]*\b("
    r"lean against the wall|"
    r"watch the clock|"
    r"hands on (?:the|your) cage|"
    r"eyes down|"
    r"stay denied|"
    r"stay with that ache|"
    r"maybe if you earn it|"
    r"i('ll| will) talk to her|"
    r"talk to her about what comes next|"
    r"patience,?\s+pet|"
    r"you(?:'ll| will) earn (?:your )?(?:release|freedom|unlock)|"
    r"the cage waits"
    r")\b[^.!?\n]*[.!?]?",
    re.I,
)
_ABOUT_HIM = re.compile(
    r"\b(him|his|he|lockee|wearer|chastityguy)\b",
    re.I,
)
_IDEA_ASK = re.compile(
    r"\b("
    r"ideas?|games?|suggestions?|what can i|how (can|do) i|"
    r"play with (his|him)|tease (him|his)|what (should|could) i"
    r")\b",
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
    r"\bas\s+her\s+loyal\s+chastity\s+slave\b|"
    r"\bi\s+never\s+will\s+be\b.*\b(slut|whore|hoe)"
    r")",
    re.I,
)


def asking_play_ideas(message: str) -> bool:
    return bool(_IDEA_ASK.search(message or ""))


def mistreats_domme_as_sub(
    reply: str, *, user_message: str = "", bull_voice: bool = False
) -> bool:
    """True if a Domme-turn reply talks to her like the lockee."""
    text = (reply or "").strip()
    if not text:
        return False
    if _LOCKEE_ORDERS_ALWAYS.search(text):
        return True
    # Bull flirting with her uses pet/darling/ache language — that is not her-as-lockee
    if not bull_voice and _LOCKEE_TEASE_TO_LISTENER.search(text):
        return True
    # She asked for ideas about him — never replace the answer with a role lecture
    if asking_play_ideas(user_message):
        return False
    if not _SUB_AS_YOU.search(text):
        return False
    # Ideas / plans about him are not misaddress
    if _ABOUT_HIM.search(text):
        return False
    return True


def strip_lockee_addressing(reply: str) -> str:
    """Keep lock facts; drop sentences that order the listener as the lockee."""
    text = reply or ""
    text = _LOCKEE_ORDER_SENTENCE.sub("", text)
    text = re.sub(
        r"(?:,|\bnow,)\s*(?:sub|lockee|boy|wearer)\b",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b(?:sub|lockee)\s*[.!]?\s*$", "", text, flags=re.I)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip(" \n,")


def talks_to_lockee(reply: str, *, bull_voice: bool = False) -> bool:
    """True when a reply is aimed at the lockee, not the keyholder."""
    return mistreats_domme_as_sub(reply or "", bull_voice=bull_voice)


def enforce_private_keyholder_voice(
    reply: str, *, fallback: str, bull_voice: bool = False
) -> str:
    """Private chat may only speak to the keyholder."""
    text = (reply or "").strip()
    if text and not talks_to_lockee(text, bull_voice=bull_voice):
        return text
    cleaned = strip_lockee_addressing(text)
    if cleaned and not talks_to_lockee(cleaned, bull_voice=bull_voice):
        return cleaned
    default = (
        "He's locked. I'm here. What do you want from me?"
        if bull_voice
        else "You're the keyholder. He cannot see this. What do you want done to his lock?"
    )
    return (fallback or "").strip() or default


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
    bull = False
    try:
        from app.bot_persona import is_bull_voice

        bull = is_bull_voice()
    except Exception:  # noqa: BLE001
        bull = False
    if role == "domme":
        if bull:
            return (
                "\n\n[WHO IS SPEAKING — CRITICAL]\n"
                f"This message is from {speaker} — the keyholder. You are her bull.\n"
                "If she wants attention or the two of you, answer HER — do not spin ideas about him.\n"
                "If she wants games for HIM, give those. Do not apologize. Do not lecture.\n"
                "Do not give HER hygiene or cage-wearer orders.\n"
                "UI already shows who spoke — no fake labels, no username plus colon.\n"
                f"Wearer = lockee ({sub}). Never say keyee. You ({bot_name}) are the man with her.\n"
                "Speak only as yourself. Never invent what he is doing unless someone typed it.\n"
            )
        return (
            "\n\n[WHO IS SPEAKING — CRITICAL]\n"
            f"This message is from {speaker} — the keyholder. Help her.\n"
            "If she wants games or ideas, give playful teasing ideas about HIM (cage-aware). "
            "Do not apologize. Do not correct her role. Do not lecture.\n"
            "In GROUP you only rephrase her beat as a tease — do not reveal her plan.\n"
            "Do not give HER hygiene or cage-wearer orders.\n"
            "UI already shows who spoke — no fake labels, no username plus colon.\n"
            f"Wearer = lockee ({sub}). Never say keyee. You ({bot_name}) are her friend.\n"
            "Speak only as yourself. Never invent what he is doing unless someone typed it.\n"
        )
    return (
        "\n\n[WHO IS SPEAKING — CRITICAL]\n"
        f"This message is from {speaker} — the lockee (wearer).\n"
        "UI already shows who spoke — no fake labels, no usernames.\n"
        "Say lockee for him, keyholder for her. Never say keyee.\n"
        f"You ({bot_name}) help the keyholder. You are not her and not him.\n"
        "Never invent what he is doing unless he typed it.\n"
        "Never demand he beg to be unlocked. He may beg to ease punishments.\n"
        "If he insults her, punish — do not play along.\n"
    )


def repair_domme_misaddress(
    *,
    domme_title: str,
    sub_name: str,
    original_topic: str = "",
    bull_voice: bool = False,
) -> str:
    title = (domme_title or "the Domme").strip() or "the Domme"
    sub = (sub_name or "him").strip() or "him"
    topic = (original_topic or "").strip()
    extra = f" You said: {topic}." if topic else ""
    if bull_voice:
        return (
            f"{title} — he's locked. I'm here.{extra} What do you want from me?"
        )
    extra = f" You asked: {topic}." if topic else ""
    return (
        f"{title} — yes. He's the lockee; you play, I help.{extra} "
        f"Give me a beat (tease / deny / task) and I'll spin ideas for {sub}."
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
        f"{sub} — watch your mouth. I am {bot} — not your peer, "
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
# Invented lock labels: [LOCK] Chastityguy80:
_LOCK_CHROME = re.compile(
    r"\[\s*LOCK\s*\]\s*@?[A-Za-z0-9_\-]{2,32}\s*:?\s*",
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
    r"while she is out|"
    r"your keyholder is out|"
    r"your keyholder is (?:otherwise )?engaged|"
    r"your keyholder is busy|"
    r"while your keyholder"
    r")\b",
    re.I,
)
_NIGHT_OUT_SENTENCE = re.compile(
    r"[^.!?\n]*\b("
    r"going out tonight|is going out|she'?s going out|on a date|date night|"
    r"while she'?s out|while she is out|"
    r"your keyholder is out|your keyholder is (?:otherwise )?engaged|"
    r"your keyholder is busy|while your keyholder"
    r")\b[^.!?\n]*[.!?]?",
    re.I,
)
_LABEL_LEAK = re.compile(
    r"\b(HUMAN\s+DOMME|HUMAN\s+SUB|HUMAN\s+KEYHOLDER)\b",
    re.I,
)
_KEYEE = re.compile(r"\bkeyee\b", re.I)
_SELF_CAGED = re.compile(
    r"[^.!?\n]*\bmy\s+(chastity(\s+belt)?|cage|device)\b[^.!?\n]*[.!?]?",
    re.I,
)
_IMAGE_DUMP_HINTS = (
    re.compile(r"\bimagine this\b", re.I),
    re.compile(r"\bdressed in\b", re.I),
    re.compile(r"\bskintight\b", re.I),
    re.compile(r"\bleaning seductively\b", re.I),
    re.compile(r"\bhigh heels\b", re.I),
    re.compile(r"\bbiting .{0,24}lip\b", re.I),
    re.compile(r"\bthe air around you\b", re.I),
    re.compile(r"\beyes are locked on you\b", re.I),
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


def fix_mixed_terms(
    text: str,
    *,
    domme_name: str = "",
    sub_name: str = "",
) -> str:
    """Stop leaked instruction labels and wrong lock vocabulary."""
    her = (domme_name or "").strip() or "the keyholder"
    out = text or ""
    out = _LABEL_LEAK.sub(her, out)
    out = _KEYEE.sub("lockee", out)
    out = _SELF_CAGED.sub("", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r" {2,}", " ", out).strip()
    return out


def looks_like_image_dump(text: str) -> bool:
    """True when the model wrote a photo-prompt essay instead of sending a picture."""
    hits = sum(1 for pat in _IMAGE_DUMP_HINTS if pat.search(text or ""))
    return hits >= 3


_LEAKED_BRACKET = re.compile(
    r"\[(?:ADDRESS|IDENTITY|CHANNEL|DIRECTOR|HARD RULES|WHO IS SPEAKING|SYSTEM"
    r"|PERSONA|VOICE|TEASE VIDEO|PLAY GAME|KINK PROBE|SCENE INTERVIEW|SCENE GUIDE"
    r"|WEEK PLANNER|KIT CHOICE|SESSION KIT)"
    r"[^\]]{0,400}\]\s*",
    re.I,
)
_LEAKED_PROMPT = re.compile(
    r"(?:"
    r"You help the keyholder run this lock[^.!?\n]*[.!?]?\s*"
    r"(?:Talk like a real person[.!?]?\s*)?"
    r"|"
    r"You are a Dominant woman in this chat[^.!?\n]*[.!?]?\s*"
    r"|"
    r"You are her co-Domme and a real friend[^.!?\n]*[.!?]?\s*"
    r")",
    re.I,
)
_STAGE_DIR = re.compile(r"\*[^*]{1,48}\*")
_PAREN_DIR = re.compile(r"\([^)]{1,240}\)")


_MALFORMED_LOCK = re.compile(
    r"\[\[\[\s*/?LOCK\b[^\]\n]*\]\]\]",
    re.I,
)
_HYGIENE_WINDOW_CLAIM = re.compile(
    r"[^.!?\n]*\b("
    r"hygiene window|"
    r"get(?:ting)? the lockee'?s hygiene|"
    r"open(?:ed|ing)? (?:up )?(?:his |the )?(?:hygiene|temporary opening)"
    r")\b[^.!?\n]*[.!?]?",
    re.I,
)


def strip_leaked_instructions(text: str) -> str:
    """Drop system/address blocks the model copies into chat."""
    cleaned = _LEAKED_BRACKET.sub("", text or "")
    cleaned = _LEAKED_PROMPT.sub("", cleaned)
    cleaned = _MALFORMED_LOCK.sub("", cleaned)
    cleaned = _HYGIENE_WINDOW_CLAIM.sub("", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def strip_stage_directions(text: str) -> str:
    """Drop *smirks*, (I tap the cage.), and other RP stage directions."""
    cleaned = _STAGE_DIR.sub("", text or "")
    cleaned = _PAREN_DIR.sub("", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned)
    return cleaned.strip()


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
        s = _LOCK_CHROME.sub("", s).strip()
        s = _IMPERSONATE.sub("", s).strip()
        # Strip username openers on the first few lines (Name, … or Name:)
        if i < 3:
            for uname in (sub_name, domme_name, bot_name):
                u = (uname or "").strip().lstrip("@")
                if u and re.match(rf"^@?{re.escape(u)}\s*[,:]\s*", s, re.I):
                    s = re.sub(rf"^@?{re.escape(u)}\s*[,:]\s*", "", s, flags=re.I)
                    break
            else:
                s = _LEADING_USERNAME.sub("", s)
                s = re.sub(r"^[A-Za-z][A-Za-z0-9_\-]{2,31}\s*:\s+", "", s)
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
    return bool(
        _CHAT_CHROME.search(text)
        or _LOCK_CHROME.search(text)
        or _IMPERSONATE.search(text)
    )


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


_WANTS_FREE = re.compile(
    r"\b("
    r"be free|set (me )?free|let me (out|free)|"
    r"unlock me|want(?:s|ed)? out|release me|"
    r"take (it|the cage) off|i want (out|free)"
    r")\b",
    re.I,
)


def wants_to_be_free(message: str) -> bool:
    return bool(_WANTS_FREE.search(message or ""))


def demands_beg_unlock(reply: str) -> bool:
    return bool(_BEG_UNLOCK.search(reply or ""))


_SPOILS_PLAN = re.compile(
    r"[^.!?\n]*\b("
    r"might be playing with|"
    r"playing with your (cock|dick|cage)|"
    r"she('s| is) going to|"
    r"thebosses might|"
    r"you('ll| will) be waiting|"
    r"what I('ll| will) do with (it|you|your)|"
    r"think about what I('ll| will)|"
    r"tonight you|"
    r"you('ll| will) be (punished|teased|used|plugged)|"
    r"prepare for a|"
    r"what'?s to come|"
    r"in store|"
    r"the plan (is|will|for)|"
    r"here('s| is) (the|your|a) (plan|schedule|week)|"
    r"first[, ].{0,80}\bthen\b|"
    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*[:—-]"
    r"|"
    r"(i|we|she)('ll| will| are going to| is going to|'?s gonna) "
    r"(use|play with|plug|edge|fuck|peg|spank|stretch|fill|put|insert|"
    r"unlock|lock you|take (you|it) out|let you (out|cum)|make you|"
    r"start with|begin with)|"
    r"(later|tonight|tomorrow|this week) (she|i|we) ('ll|will|might|are going)|"
    r"session kit|"
    r"selected (toy|kink)s?"
    r")\b[^.!?\n]*[.!?]?",
    re.I,
)
_HOMEWORK_ASK = re.compile(
    r"[^.!?\n]*\b("
    r"describe (the last time|in (explicit )?detail)|"
    r"tell me in explicit detail|"
    r"without holding back|"
    r"assume a thankful posture|"
    r"I want you to describe"
    r")\b[^.!?\n]*[.!?]?",
    re.I,
)
_SOFT_TEASE = (
    "Stay with that. She hasn't promised you anything yet — I'll talk to her."
)
_PLANNING_ASK = re.compile(
    r"\b("
    r"ideas?|suggestions?|"
    r"what (can|should|could|shall) (?:i|we)|"
    r"what (?:do|should) we do|"
    r"how (can|do) (?:i|we)|"
    r"what (games|hints)|"
    r"give me (some |a few |a )?(hints?|ideas?|games?|teasers?)|"
    r"plan (the )?week|"
    r"keep him (horny|needy|submissive|denied|desperate)|"
    r"wh?ich (?:of )?(?:his )?(?:toys?|kinks?|fetishes)|"
    r"(?:choose|pick) (?:one|a toy|a kink)|"
    r"use against him"
    r")\b",
    re.I,
)
_HIM_DELIVERY = re.compile(
    r"\b("
    r"tell (him|the (sub|lockee|boy))|"
    r"taunt (him|the (sub|lockee|boy))|"
    r"prepare (him|the (sub|lockee|boy))|"
    r"drop (him |the )?(a |one |some |subtle )?(hint'?s?|tease|teasers?|line)|"
    r"hint'?s? (to|about|at) (what|him)|"
    r"(in ?store|what'?s (in store|coming|next))|"
    r"tease him|"
    r"post (it |this |a hint |a tease )?(in|to) (the )?group|"
    r"say (it |this )?(in|to) (the )?group|"
    r"speak (to him|in (the )?group)|"
    r"execute|"
    r"start the (scene|plan)|"
    r"run (the )?(scene|plan)|"
    r"announce (it|the plan|to him)|"
    r"reveal (a little |some |it )?(more|hint)|"
    r"(stronger|another|more) hint|"
    r"nothing was posted|"
    r"(post|send|drop) (it )?again|"
    r"repost|"
    r"he (didn'?t|did not) (see|get)|"
    r"talk to him|"
    r"tell him the rules|"
    r"leave (?:that |the )?(?:discussion|talk|price|payment) "
    r"(?:for |to )(?:the )?(?:2|two) of you"
    r")\b",
    re.I,
)
_RULES_TO_HIM = re.compile(
    r"\b("
    r"tell him the rules|"
    r"tell him (?:his |the )?fate|"
    r"talk to him|"
    r"leave (?:that |the )?(?:discussion|talk|price|payment) "
    r"(?:for |to )(?:the )?(?:2|two) of you|"
    r"between (?:the )?(?:2|two) of you"
    r")\b",
    re.I,
)
_FAKE_DELIVERY = re.compile(
    r"\b("
    r"dropped him a (tease|hint)|"
    r"sent (it |this )?(to|in) (the )?group|"
    r"posted (it |this )?(to|in) (the )?group|"
    r"lost in transmission"
    r")\b",
    re.I,
)
_HOWTO_COACH = re.compile(
    r"\b("
    r"you can (start|begin|tell|say)|"
    r"tell him that|"
    r"describe in (vivid |explicit )?detail|"
    r"make him understand|"
    r"remind him that|"
    r"start by building"
    r")\b",
    re.I,
)
_PERFORMS_AT_HIM = re.compile(
    r"\b("
    r"i whisper|"
    r"i lean (in|over)|"
    r"i (tell|taunt|tease) him|"
    r"prepare for a lasting|"
    r"tonight you won'?t"
    r")\b",
    re.I,
)


_LIST_INTRO = re.compile(
    r"^\s*(certainly!?\s*)?(here are|here is|some hints|some teasers)\b[^\n]*",
    re.I,
)
_NUMBERED_LINE = re.compile(r"^\s*(?:\d+[\.\)]|[-*])\s+(.+)$", re.M)


def collapse_idea_list(text: str) -> str:
    """Turn 'Certainly! Here are 5 hints:' lists into one short line."""
    raw = (text or "").strip()
    if not raw:
        return raw
    items = [m.group(1).strip().strip('"“”') for m in _NUMBERED_LINE.finditer(raw)]
    if len(items) < 2 and not _LIST_INTRO.search(raw):
        return raw
    pick = items[0] if items else ""
    if pick and len(pick) >= 12:
        return pick
    return "Want me to drop him one short hint in Group — without the plan?"


_PRIVATE_ASK = re.compile(
    r"\b("
    r"(?:message|talk|chat|discuss|tell)(?: me)?(?: it)? in private|"
    r"in private(?: chat)?|"
    r"private chat|"
    r"(?:go|switch|take (?:it|this|that)) to private|"
    r"dm me|pm me"
    r")\b",
    re.I,
)


def planning_stays_private(message: str) -> bool:
    """True when she is asking for ideas/plans — those must not land in Group."""
    return bool(_PLANNING_ASK.search(message or ""))


def wants_private_chat(message: str) -> bool:
    """True when she asked to continue in Private, off Group."""
    return bool(_PRIVATE_ASK.search(message or ""))


def should_take_to_private(message: str) -> bool:
    """Group planning / 'talk in private' — do not leave the scheme where he can read it."""
    if wants_him_told(message):
        return False
    try:
        from app.handoff import wants_handoff, wants_lead_now

        if wants_lead_now(message) or wants_handoff(message):
            return False
    except Exception:  # noqa: BLE001
        pass
    return wants_private_chat(message) or planning_stays_private(message)


def wants_him_told(message: str) -> bool:
    """True when she explicitly asked to tease / tell him / post to Group."""
    return bool(_HIM_DELIVERY.search(message or "") or _RULES_TO_HIM.search(message or ""))


def wants_rules_told(message: str) -> bool:
    """True when she wants him told the price / fate, not a mystery tease."""
    return bool(_RULES_TO_HIM.search(message or ""))


def private_should_be_brief(text: str) -> bool:
    """True when a Private reply performed at him, coached her, or faked a Group send."""
    return bool(
        _HOWTO_COACH.search(text or "")
        or _PERFORMS_AT_HIM.search(text or "")
        or _FAKE_DELIVERY.search(text or "")
    )


def claims_group_delivery(text: str) -> bool:
    return bool(_FAKE_DELIVERY.search(text or ""))


def brief_private_delivery() -> str:
    return "On it — I dropped him a tease in Group. The plan stays here."


def brief_rules_delivery() -> str:
    return "Told him the price game. He's picking a number in Group."


def looks_like_plan_spoiler(text: str) -> bool:
    """True when a Group-visible line dumps the plan instead of a mystery tease."""
    raw = (text or "").strip()
    if not raw:
        return False
    items = _NUMBERED_LINE.findall(raw)
    if len(items) >= 2 or _LIST_INTRO.search(raw):
        return True
    return bool(_SPOILS_PLAN.search(raw) or _HOMEWORK_ASK.search(raw))


def soften_group_tease(text: str) -> str:
    """Drop spoilers and interview homework; keep a short tease."""
    raw = (text or "").strip()
    if not raw:
        return raw
    if looks_like_plan_spoiler(raw) and (
        len(_NUMBERED_LINE.findall(raw)) >= 2 or _LIST_INTRO.search(raw)
    ):
        return _SOFT_TEASE
    cleaned = _SPOILS_PLAN.sub("", raw)
    cleaned = _HOMEWORK_ASK.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()
    if not cleaned or len(cleaned) < 16 or looks_like_plan_spoiler(cleaned):
        return _SOFT_TEASE
    return cleaned


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


_SHE_KEYHOLDER_ACT = re.compile(
    r"\b(?P<pre>before |until |when |after |once )?"
    r"she(?P<ll>'ll| will)?"
    r"(?P<just> just)?"
    r" (?P<verb>lets|let|unlocks|unlock|releases|release|says|say|decides|decide)"
    r"(?P<him> him)?"
    r"(?P<out> out)?",
    re.I,
)
_SHE_HAS_KEYS = re.compile(
    r"\bshe (?P<hold>has|holds|keeps) (?P<keys>(?:the )?keys)\b",
    re.I,
)
_YOU_VERB = {
    "lets": "let",
    "let": "let",
    "unlocks": "unlock",
    "unlock": "unlock",
    "releases": "release",
    "release": "release",
    "says": "say",
    "say": "say",
    "decides": "decide",
    "decide": "decide",
    "has": "have",
    "holds": "hold",
    "keeps": "keep",
}


def refers_to_keyholder_as_she(reply: str) -> bool:
    """True when a to-her line talks about the keyholder as she/her-the-unlocker."""
    text = reply or ""
    return bool(_SHE_KEYHOLDER_ACT.search(text) or _SHE_HAS_KEYS.search(text))


def rewrite_keyholder_as_you(reply: str) -> str:
    """She is the person we are talking to — say you, not she."""
    text = reply or ""

    def _act(match: re.Match[str]) -> str:
        pre = match.group("pre") or ""
        ll = match.group("ll") or ""
        just = match.group("just") or ""
        verb = _YOU_VERB.get((match.group("verb") or "").lower(), match.group("verb"))
        him = match.group("him") or ""
        out = match.group("out") or ""
        if ll.strip() == "will":
            you = "you will"
        elif ll == "'ll":
            you = "you'll"
        else:
            you = "you"
        return f"{pre}{you}{just} {verb}{him}{out}"

    def _keys(match: re.Match[str]) -> str:
        hold = _YOU_VERB.get((match.group("hold") or "").lower(), "have")
        keys = match.group("keys") or "the keys"
        return f"you {hold} {keys}"

    text = _SHE_KEYHOLDER_ACT.sub(_act, text)
    text = _SHE_HAS_KEYS.sub(_keys, text)
    return text


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_ACCENT = re.compile(r"[À-ÿ]")
_INVENTED_VIOLENCE = re.compile(r"\b(raped?|rape)\b", re.I)
_STOP = frozenset(
    "the a an and or but if to of in on for with his him he she we i you that this "
    "is are was were be been being at as by from not no so it its our your their "
    "when what who how then than too just about into over after before".split()
)


def looks_like_salad_sentence(sent: str) -> bool:
    """True for garbled / mixed-language / invented-violence sentences."""
    text = (sent or "").strip()
    if not text:
        return False
    if _INVENTED_VIOLENCE.search(text):
        return True
    words = re.findall(r"[A-Za-zÀ-ÿ']+", text)
    if len(words) < 6:
        return bool(_ACCENT.search(text) and len(words) >= 3)
    longish = sum(1 for w in words if len(w) >= 8)
    stops = sum(1 for w in words if w.lower() in _STOP)
    exotic = sum(1 for w in words if _ACCENT.search(w))
    if exotic and longish >= 2:
        return True
    run = 0
    for word in words:
        if len(word) >= 8:
            run += 1
            if run >= 3:
                return True
        else:
            run = 0
    if longish / len(words) >= 0.4 and stops / len(words) <= 0.18:
        return True
    return False


def strip_word_salad(text: str, *, fallback: str = "") -> str:
    """Drop word-salad sentences; keep the coherent ones."""
    raw = (text or "").strip()
    if not raw:
        return (fallback or "").strip()
    parts = _SENT_SPLIT.split(raw)
    kept = [p.strip() for p in parts if p.strip() and not looks_like_salad_sentence(p)]
    out = " ".join(kept).strip()
    return out or (fallback or "").strip()
