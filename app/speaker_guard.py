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


def addressing_block(
    *,
    role: str,
    speaker: str,
    domme_title: str,
    sub_name: str,
    bot_name: str,
) -> str:
    title = (domme_title or "Mistress").strip() or "Mistress"
    sub = (sub_name or "the Sub").strip() or "the Sub"
    if role == "domme":
        return (
            "\n\n[WHO IS SPEAKING — CRITICAL]\n"
            f"This message is from {speaker} — the HUMAN DOMME / Chaster KEYHOLDER.\n"
            f"She is NOT locked. She is NOT the wearer. Do NOT give HER hygiene unlocks, "
            f"orders to kneel, or talk about 'your cage' as hers.\n"
            f"Address her as {title}. Confirm orders TO her. "
            f"The lockee is {sub} — refer to him as he/him/BOY.\n"
            f"You ({bot_name}) are her co-Domme / AI keyholder partner.\n"
        )
    return (
        "\n\n[WHO IS SPEAKING — CRITICAL]\n"
        f"This message is from {speaker} — the HUMAN SUB / Chaster WEARER (lockee).\n"
        f"Speak to him as the locked boy. {title} is the human Domme (separate person).\n"
        f"You ({bot_name}) are AI Domme/keyholder. Never confuse him with {title}.\n"
    )


def repair_domme_misaddress(
    *,
    domme_title: str,
    sub_name: str,
    original_topic: str = "",
) -> str:
    title = (domme_title or "Mistress").strip() or "Mistress"
    sub = (sub_name or "him").strip() or "him"
    topic = (original_topic or "").strip()
    extra = f" About your order ({topic}): noted — I'll keep control of {sub}." if topic else ""
    return (
        f"{title} — sorry, that was aimed wrong. You're the keyholder, not the lockee.\n"
        f"I answer to you; {sub} is the one in the cage.{extra}"
    )
