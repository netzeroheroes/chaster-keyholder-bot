"""Question the lockee to discover kinks, toys, and buttons to use against him."""

from __future__ import annotations

import re
from typing import Any

from app.denial import apply_kink_limit_updates, parse_kink_limit_updates

_CANCEL_RE = re.compile(
    r"\b("
    r"cancel(?:\s+the)?\s+(?:interview|probe|grilling)|"
    r"stop\s+(?:interviewing|grilling|questioning)(?:\s+him)?|"
    r"enough\s+questions|"
    r"forget\s+(?:the\s+)?(?:interview|grilling)"
    r")\b",
    re.I,
)

_START_RE = re.compile(
    r"\b("
    r"interview him|"
    r"grill him|"
    r"question him|"
    r"interrogate him|"
    r"find out (?:his |the )?(?:kinks?|toys?|buttons|limits?)|"
    r"discover (?:his )?(?:kinks?|toys?)|"
    r"ask him (?:about )?(?:his )?(?:kinks?|toys?|limits?|buttons)|"
    r"what (?:toys?|kinks?) (?:can we|should we|to) use against him|"
    r"kink (?:intake|interview|probe|interrogation)|"
    r"tools to use against him"
    r")\b",
    re.I,
)

_GO_GROUP_RE = re.compile(
    r"\b("
    r"do it now|ask him(?: now)?|go(?:\s+to)?\s+group|"
    r"start (?:now|in group)|grill him now|"
    r"tell him|question him (?:in|on) group"
    r")\b",
    re.I,
)

_SKIP_RE = re.compile(
    r"\b(skip|pass|next|i don'?t know|not sure|none|nothing)\b",
    re.I,
)

_STEPS: tuple[tuple[str, str], ...] = (
    (
        "kinks",
        "What kinks and fetishes actually get to you — the ones we can use against you?",
    ),
    (
        "toys",
        "What toys or tools do you have, and which ones wreck you fastest?",
    ),
    (
        "buttons",
        "What hits hardest — humiliation, cuckold/bull, SPH, denial, pain, service — name it.",
    ),
    (
        "limits",
        "Hard limits first, then soft. What is off the table?",
    ),
    (
        "genre",
        "What porn or lock flavour do you leak to when you're desperate? Be specific.",
    ),
)


def empty_probe() -> dict[str, Any]:
    return {
        "active": False,
        "step": "kinks",
        "answers": {},
        "go_group": False,
    }


def start_probe(*, go_group: bool = False) -> dict[str, Any]:
    probe = empty_probe()
    probe["active"] = True
    probe["go_group"] = bool(go_group)
    return probe


def wants_kink_probe(message: str) -> bool:
    return bool(_START_RE.search(message or ""))


def wants_cancel_probe(message: str) -> bool:
    return bool(_CANCEL_RE.search(message or ""))


def wants_probe_go(message: str) -> bool:
    return bool(_GO_GROUP_RE.search(message or ""))


def current_question(probe: dict[str, Any] | None) -> str:
    step = str((probe or {}).get("step") or "kinks")
    for key, question in _STEPS:
        if key == step:
            return question
    return ""


def _next_missing(probe: dict[str, Any]) -> str:
    answers = probe.get("answers") if isinstance(probe.get("answers"), dict) else {}
    for key, _ in _STEPS:
        if not str(answers.get(key) or "").strip():
            return key
    return "done"


def apply_probe_answer(
    probe: dict[str, Any],
    message: str,
    *,
    memory: Any | None = None,
) -> dict[str, Any]:
    out = dict(probe or empty_probe())
    out["active"] = True
    answers = dict(out.get("answers") or {})
    text = (message or "").strip()
    step = str(out.get("step") or "kinks")
    if text and not wants_kink_probe(text) and not wants_cancel_probe(text):
        if _SKIP_RE.fullmatch(text) or (
            _SKIP_RE.search(text) and len(text) < 24
        ):
            answers[step] = answers.get(step) or "(skipped)"
        else:
            answers[step] = text[:500]
            if memory is not None:
                bits = parse_kink_limit_updates(text)
                if step == "limits" and not bits.get("hard_limits"):
                    bits = {**bits, "hard_limits": _split_limits(text)}
                    bits = {k: v for k, v in bits.items() if v}
                if bits:
                    apply_kink_limit_updates(memory, bits)
    out["answers"] = answers
    nxt = _next_missing(out)
    out["step"] = nxt
    if nxt == "done":
        out["active"] = False
        out["go_group"] = False
    return out


def _split_limits(text: str) -> list[str]:
    parts = re.split(r"\s*(?:,|/|;|\band\b)\s*", (text or "").strip())
    out: list[str] = []
    for part in parts:
        item = part.strip(" .")
        if 2 <= len(item) <= 40:
            out.append(item)
    return out[:8]


def format_probe_director(probe: dict[str, Any], *, room: str = "group") -> str:
    step = str(probe.get("step") or "kinks")
    question = current_question(probe)
    answers = probe.get("answers") if isinstance(probe.get("answers"), dict) else {}
    have = ", ".join(
        f"{k}={str(v)[:60]}" for k, v in answers.items() if str(v).strip()
    ) or "nothing yet"
    if room == "private":
        if probe.get("go_group"):
            return (
                "\n\n[KINK PROBE — start in GROUP now]\n"
                f"Already have: {have}\n"
                "One short line to her, then [[[GROUP]]] with this one question to him:\n"
                f"{question}\n"
                "Do not dump a form. Do not invent his answers.\n"
            )
        return (
            "\n\n[KINK PROBE — collecting, still private]\n"
            f"Already have: {have}\n"
            "Tell her you will grill him in Group, one question at a time, "
            "to find kinks and tools to use against him. "
            "Ask if she wants you to start now. "
            "If she already said go / ask him / group, use a GROUP tag.\n"
            f"First question ready: {question}\n"
        )
    return (
        "\n\n[KINK PROBE — GROUP, lockee answering]\n"
        f"Already have: {have}\n"
        f"Ask him ONLY this: {question}\n"
        "One short question. Store what he says. Stay inside hard limits. "
        "Do not offer unlock. She is still the keyholder.\n"
        f"Step={step}.\n"
    )


def format_probe_summary(
    probe: dict[str, Any],
    *,
    room: str = "private",
) -> str:
    answers = probe.get("answers") if isinstance(probe.get("answers"), dict) else {}
    lines = [
        f"{label}: {answers.get(key) or '(none)'}"
        for key, label in (
            ("kinks", "Kinks"),
            ("toys", "Toys / tools"),
            ("buttons", "Buttons"),
            ("limits", "Limits"),
            ("genre", "Porn / lock flavour"),
        )
    ]
    body = "\n".join(lines)
    if room == "private":
        return (
            "\n\n[KINK PROBE — done]\n"
            "Give HER a short dossier she can weaponise. Do not dump this as a form to him.\n"
            f"{body}\n"
            "Suggest 2 ways to use it against him this lock. Stay in hard limits. "
            "Offer to add items to the session kit if she wants.\n"
        )
    return (
        "\n\n[KINK PROBE — done in GROUP]\n"
        "One mean thank-you to him. Do not read the full dossier out loud. "
        "Tell her privately (she can open Plan) that you have what you need.\n"
        f"Notes (do not paste verbatim to him):\n{body}\n"
    )
