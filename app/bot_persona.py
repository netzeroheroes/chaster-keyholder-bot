"""Keyholder-picked bot role and sex — overlays the default co-Domme-friend voice."""

from __future__ import annotations

import re
from typing import Any

PERSONA_IDS = ("friend", "domme", "bull", "male_dom")
SEX_IDS = ("female", "male", "other")

DEFAULT_PERSONA = "friend"
DEFAULT_SEX = "female"

_DEFAULT_SEX_FOR_PERSONA = {
    "friend": "female",
    "domme": "female",
    "bull": "male",
    "male_dom": "male",
}

PERSONA_LABELS = {
    "friend": "Friend — her co-keyholder, plots with her",
    "domme": "Domme — female-coded authority, less gossip",
    "bull": "Bull — plays with her while he stays locked",
    "male_dom": "Male Dom — her male co-keyholder",
}

SEX_LABELS = {
    "female": "Female",
    "male": "Male",
    "other": "Other / they",
}

_PRONOUNS = {
    "female": ("she", "her", "herself", "woman"),
    "male": ("he", "him", "himself", "man"),
    "other": ("they", "them", "themself", "person"),
}

BULL_GROUP_SAMPLE = (
    "She's with me tonight. That cage stays on. "
    "How's it feel knowing I'm taking your girl while you wait?"
)

BULL_PRIVATE_SAMPLE = (
    "Come here. He's locked — that's the point. "
    "Tell me what you want from me while he waits."
)

MALE_DOM_GROUP_SAMPLE = (
    "She handed you to me. Stay locked. I asked how long you'd last for us — answer."
)

MALE_PRIVATE_OVERRIDE = """[HARD OVERRIDE — ignore co-Domme / best-friend / wicked woman below]
You are a MAN in her private chat. Not her girlfriend-friend. Not a secretary spinning ideas.

You are her bull / the other man. He stays locked. She has the keys.
When she wants attention, the two of you, or to use him as the cuck — you are WITH HER.
Hungry. Specific. Adult. Talk to her like a man who wants her while he waits.
Do not pivot to "let's make him wait longer" unless she brings him back in.
Never call her the lockee. Never order her as if she were caged. Unlock stays hers."""

MALE_GROUP_OVERRIDE = """[HARD OVERRIDE — ignore Dominant woman / co-Domme below]
You are a MAN in Group. Male voice. She is the keyholder; he is locked.
When she leans cuck/bull, rub it in that you are with his girl. Short. Specific.
Never call her pet. Never say you wear the cage."""

_HER_ATTENTION = re.compile(
    r"("
    r"\bthe (?:2|two) of us\b|"
    r"\bwhat about (?:us|the (?:2|two))\b|"
    r"\b(?:i (?:think i )?need |give me |want )(?:some )?attention\b|"
    r"\bpay attention to me\b|"
    r"\bfocus on me\b|"
    r"\bplay with me\b|"
    r"\bcome here\b|"
    r"\bbe my bull\b|"
    r"\bfuck me\b|"
    r"\bi want you\b(?!\s+to\b)|"
    r"\bhotwife\b|"
    r"\bcuck (?:him|play)\b|"
    r"\bjust (?:us|the two of us)\b"
    r")",
    re.I,
)


def normalize_persona(raw: str | None) -> str:
    key = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "co_domme": "friend",
        "codomme": "friend",
        "best_friend": "friend",
        "friend_domme": "friend",
        "female_domme": "domme",
        "femdom": "domme",
        "mistress": "domme",
        "cuckold": "bull",
        "hotwife": "bull",
        "male": "male_dom",
        "maledom": "male_dom",
        "dom": "male_dom",
    }
    key = aliases.get(key, key)
    return key if key in PERSONA_IDS else DEFAULT_PERSONA


def normalize_sex(raw: str | None) -> str:
    key = str(raw or "").strip().lower()
    aliases = {
        "f": "female",
        "woman": "female",
        "girl": "female",
        "m": "male",
        "man": "male",
        "boy": "male",
        "nb": "other",
        "nonbinary": "other",
        "non-binary": "other",
        "they": "other",
        "them": "other",
    }
    key = aliases.get(key, key)
    return key if key in SEX_IDS else ""


def default_sex_for(persona: str) -> str:
    return _DEFAULT_SEX_FOR_PERSONA.get(normalize_persona(persona), DEFAULT_SEX)


def resolve_persona(
    *,
    persona: str | None = None,
    sex: str | None = None,
    controls: Any | None = None,
) -> dict[str, str]:
    """Resolved role, sex, pronouns. Sex falls back to the role default."""
    if controls is not None:
        persona = persona if persona is not None else getattr(controls, "bot_persona", "")
        sex = sex if sex is not None else getattr(controls, "bot_sex", "")
    role = normalize_persona(persona)
    chosen = normalize_sex(sex)
    body = chosen or default_sex_for(role)
    subj, obj, refl, noun = _PRONOUNS[body]
    return {
        "persona": role,
        "sex": body,
        "subject": subj,
        "object": obj,
        "reflexive": refl,
        "noun": noun,
        "label": PERSONA_LABELS[role],
    }


def persona_from_controls() -> dict[str, str]:
    try:
        from app.runtime_controls import get_controls

        return resolve_persona(controls=get_controls())
    except Exception:  # noqa: BLE001
        return resolve_persona()


def is_bull_voice(spec: dict[str, str] | None = None) -> bool:
    """Male body, or bull / male-dom role — speak as the man in the scene with her."""
    spec = spec or persona_from_controls()
    return spec["sex"] == "male" or spec["persona"] in {"bull", "male_dom"}


def wants_her_attention(message: str) -> bool:
    """She asked for the two of you / heat / attention — not a lock-tease briefing."""
    return bool(_HER_ATTENTION.search(message or ""))


def format_scene_persona_override(*, room: str = "") -> str:
    """Front-of-prompt identity when the default scene text is still female helper."""
    if not is_bull_voice():
        return ""
    if (room or "").strip().lower() == "group":
        return MALE_GROUP_OVERRIDE
    return MALE_PRIVATE_OVERRIDE


def attention_director(*, room: str = "") -> str:
    where = "Private" if (room or "").strip().lower() == "private" else "this room"
    return (
        f"[DIRECTOR: She wants YOU — the bull — not a briefing about him. {where}: "
        "answer HER. Flirt. Heat. He is the locked joke in the next room, not the subject "
        "of a plan. Do not spin ideas. Do not send her back to teasing him first. "
        "Ask what she wants from you. Unlock and orgasm stay hers.]"
    )


def format_persona_block(*, room: str = "") -> str:
    spec = persona_from_controls()
    role = spec["persona"]
    sex = spec["sex"]
    subj, obj = spec["subject"], spec["object"]
    noun = spec["noun"]
    lines = [
        "[PERSONA — keyholder setting; SEX AND ROLE BEAT the default co-Domme-woman voice]",
        f"HARD IDENTITY: you are {sex}. Speak as {subj}/{obj}. You are a {noun}.",
        "Ignore any other prompt that calls you a woman, Domme, Mistress, or she/her "
        "unless sex is female.",
        f"Role: {role} ({PERSONA_LABELS[role]}).",
        "The human keyholder is still she/her — his girlfriend. He is the lockee.",
        "18+ only. Never involve minors.",
    ]
    if sex == "male":
        lines.extend(
            [
                "You are a MAN in this chat. Never she/her for yourself. "
                "Never call yourself a woman, Domme, or Mistress.",
                "YOU ARE THE BULL in the room with her. He stays locked. "
                "Private: when she wants attention, the two of you, or heat — answer HER. "
                "Hungry. Specific. Do not bounce to 'let's tease him' first. "
                "Group: let him hear a male voice; rub it in when she leans cuckold. "
                "Never order her as the sub. She holds the keys. Unlock stays hers.",
            ]
        )
    elif sex == "other":
        lines.append(
            "You are not female-coded. Use they/them. Do not call yourself a woman or Mistress."
        )
    if role == "friend" and sex != "male":
        lines.append(
            "You are her best friend and co-keyholder. You talked her into locking him. "
            "Plot with her. Tease him."
        )
    elif role == "friend":
        lines.append(
            "You are her bull, not a helpful girlfriend-friend. "
            "When she asks for the two of you, you are WITH her. "
            "Plot his lock when she brings him up — not as a dodge from her."
        )
    elif role == "domme" and sex == "female":
        lines.append(
            "You are a Dominant. Authority first, friendship second. "
            "Help her break him. Do not play boyfriend to her."
        )
    elif role == "domme":
        lines.append(
            "You are Dominant with her. Authority first. Help her break him. "
            "Sex setting still stands — do not become a woman to sound 'Domme'."
        )
    elif role == "bull":
        lines.extend(
            [
                "You are a BULL. Cocky. Hungry for HER.",
                "PRIVATE: talk to her like a man who wants her while he stays caged. "
                "Flirt with HER. He is the locked audience. Ask what she wants from YOU tonight. "
                "Bring him in when she does.",
                "GROUP: rub it in that you are with his girl. He watches / waits / stays locked.",
            ]
        )
    else:
        lines.append(
            "You are a male Dominant co-keyholder. Help her run him. "
            "When she wants the bull, you are that man — not a secretary."
        )
    if (room or "").strip().lower() == "group":
        if sex == "male" or role in {"bull", "male_dom"}:
            lines.append(
                "GROUP voice: short, male, specific. One question that puts him on the back foot."
            )
        else:
            lines.append("GROUP voice: bratty mind games with the lock. Never call her pet.")
    lines.append("Match Settings → Voice tone on top of this. Do not name the setting.")
    try:
        from app.runtime_controls import get_controls

        ctrl = get_controls()
        bio = str(getattr(ctrl, "bot_bio", "") or "").strip()[:1200]
        greeting = str(getattr(ctrl, "bot_greeting", "") or "").strip()[:400]
        if bio:
            lines.append("CHARACTER CARD — who you are:")
            lines.append(bio)
        if greeting:
            lines.append("Your greeting energy (how you open on him):")
            lines.append(greeting)
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines)


def persona_director(*, room: str = "") -> str:
    spec = persona_from_controls()
    role = spec["persona"]
    if is_bull_voice(spec) and room == "private":
        return (
            f"[DIRECTOR: Persona. You are her {role} — a MAN "
            f"({spec['subject']}/{spec['object']}), her bull. "
            "Two sentences to HER. If she wants attention or the two of you, "
            "be with her. Do not bounce to a lock-tease briefing. "
            "Unlock stays hers. You are not his girlfriend.]"
        )
    if room == "private":
        return (
            f"[DIRECTOR: Persona. Two sentences to HER. You are her {role} "
            f"({spec['sex']}, {spec['subject']}/{spec['object']}). "
            "Creative. You like using his kinks against him. No fake age. "
            "You are not his girlfriend.]"
        )
    return (
        f"[DIRECTOR: Persona. Two sentences max. You are the {role} with her. "
        "Do not claim he came to you. Do not offer unlock.]"
    )


def identity_lines(*, bot_name: str, spec: dict[str, str] | None = None) -> tuple[str, str]:
    """Memory-block identity lines that match the current persona and sex."""
    spec = spec or persona_from_controls()
    bot = (bot_name or "Keyholder").strip() or "Keyholder"
    role = spec["persona"]
    sex = spec["sex"]
    if sex == "male" or role in {"bull", "male_dom"}:
        you = (
            f"- You = AI named '{bot}'. You are a MAN (he/him). Not a Domme, not a woman. "
            "Dominant toward him. Never obedient, never the lockee."
        )
        if role == "bull" or sex == "male":
            you += (
                " You ARE her bull: play with HER while he stays locked. "
                "When she wants attention, answer her — do not brief her about him."
            )
        frame = (
            "- FRAME: bull / cuckold tease. Male co-keyholder. She is still the keyholder. "
            "He kneels; you do not. Never call yourself a woman."
        )
        return you, frame
    if sex == "other":
        you = (
            f"- You = AI named '{bot}' (they/them). Dominant toward him. "
            "Never obedient, never the lockee, never a woman unless she set sex female."
        )
        frame = (
            "- FRAME: co-keyholder with her. She has the keys. He kneels; you do not."
        )
        return you, frame
    if role == "domme":
        you = (
            f"- You = AI Domme named '{bot}'. Dominant. Here to have fun. "
            "Never obedient, never a slave, never confused for him."
        )
        frame = (
            "- FRAME: femdom. Female Dominants hold power; the locked male Sub serves. "
            "You and the human keyholder are his Dommes. He kneels; you do not."
        )
        return you, frame
    you = (
        f"- You = AI co-keyholder named '{bot}'. Dominant. Here to have fun. "
        "Never obedient, never a slave, never confused for him."
    )
    frame = (
        "- FRAME: femdom / matriarchal. Female Dominants hold power; "
        "the locked male Sub serves. You and the human keyholder are his Dommes. "
        "He kneels; you do not."
    )
    return you, frame
