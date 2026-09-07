"""Ask the lockee in private, store what works, brief the keyholder."""

from __future__ import annotations

import re
from typing import Any

from app.denial import apply_kink_limit_updates, parse_kink_limit_updates

_CANCEL_RE = re.compile(
    r"\b("
    r"stop\s+(?:asking|questioning|interviewing)|"
    r"enough\s+questions|"
    r"cancel(?:\s+the)?\s+(?:interview|questions)|"
    r"no\s+more\s+questions"
    r")\b",
    re.I,
)

_SKIP_RE = re.compile(
    r"\b(skip|pass|next|i don'?t know|not sure|none|nothing)\b",
    re.I,
)

_STEPS: tuple[tuple[str, str], ...] = (
    (
        "ache",
        "How desperate are you right now — scale it, and what would make it worse?",
    ),
    (
        "buttons",
        "What kind of tease wrecks you fastest when you are locked?",
    ),
    (
        "fantasy",
        "What do you hope she uses against you that you have not admitted yet?",
    ),
    (
        "works",
        "Last time you were leaking — what did that? Be specific.",
    ),
    (
        "tasks",
        "What tasks or rules keep you aching instead of going numb?",
    ),
    (
        "games",
        "What kind of game would you hate losing — dice, dares, porn roulette?",
    ),
    (
        "limits",
        "Anything new that is off the table? Soft or hard.",
    ),
)

_STEP_MEMORY = {
    "ache": "arousal_notes",
    "buttons": "what_works",
    "fantasy": "what_works",
    "works": "what_works",
    "tasks": "learned_tasks",
    "games": "learned_games",
}


def empty_learn() -> dict[str, Any]:
    return {
        "active": False,
        "paused": False,
        "step": "ache",
        "answers": {},
        "cycles": 0,
        "brief_kh": False,
        "last_brief": "",
    }


def start_learn() -> dict[str, Any]:
    state = empty_learn()
    state["active"] = True
    return state


def wants_cancel_learn(message: str) -> bool:
    return bool(_CANCEL_RE.search(message or ""))


def current_question(state: dict[str, Any] | None) -> str:
    step = str((state or {}).get("step") or "ache")
    for key, question in _STEPS:
        if key == step:
            return question
    return _STEPS[0][1]


def _next_missing(state: dict[str, Any]) -> str:
    answers = state.get("answers") if isinstance(state.get("answers"), dict) else {}
    for key, _ in _STEPS:
        if not str(answers.get(key) or "").strip():
            return key
    return "done"


def _store_answer(memory: Any, step: str, text: str) -> None:
    if memory is None or not text or text == "(skipped)":
        return
    field = _STEP_MEMORY.get(step)
    if field:
        cur = [str(x).strip() for x in (getattr(memory, field, None) or []) if str(x).strip()]
        if text.lower() not in {x.lower() for x in cur}:
            cur.append(text[:240])
        setattr(memory, field, cur[-40:])
    bits = parse_kink_limit_updates(text)
    if step == "limits" and not bits.get("hard_limits") and not bits.get("soft_limits"):
        parts = [
            p.strip(" .")
            for p in re.split(r"\s*(?:,|/|;|\band\b)\s*", text)
            if 2 <= len(p.strip(" .")) <= 40
        ]
        if parts:
            bits = {**bits, "soft_limits": parts[:6]}
    if step in {"buttons", "fantasy"} and not bits.get("kinks"):
        bits = {**bits, "kinks": [text[:80]]}
        bits = {k: v for k, v in bits.items() if v}
    if bits:
        apply_kink_limit_updates(memory, bits)
    intel = [str(x).strip() for x in (getattr(memory, "lockee_intel", None) or []) if str(x).strip()]
    label = {
        "ache": "Ache",
        "buttons": "Buttons",
        "fantasy": "Fantasy",
        "works": "What worked",
        "tasks": "Tasks he likes",
        "games": "Games he fears",
        "limits": "Limits",
    }.get(step, step)
    line = f"{label}: {text[:180]}"
    if line.lower() not in {x.lower() for x in intel}:
        intel.append(line)
    memory.lockee_intel = intel[-40:]
    if hasattr(memory, "save"):
        memory.save()


def apply_learn_answer(
    state: dict[str, Any],
    message: str,
    *,
    memory: Any | None = None,
) -> dict[str, Any]:
    out = dict(state or empty_learn())
    out["active"] = True
    out["brief_kh"] = False
    out["last_brief"] = ""
    text = (message or "").strip()
    if not text:
        out["step"] = _next_missing(out)
        return out
    if wants_cancel_learn(text):
        out["paused"] = True
        out["active"] = False
        return out
    if out.get("paused"):
        out["paused"] = False
    answers = dict(out.get("answers") or {})
    step = str(out.get("step") or "ache")
    if step == "done":
        answers = {}
        step = "ache"
        out["cycles"] = int(out.get("cycles") or 0) + 1
    if len(text) < 16 and re.match(
        r"^(hi|hey|hello|yo|sup|morning|evening)\b", text, re.I
    ):
        out["answers"] = answers
        out["step"] = step
        return out
    stored = text[:500]
    if _SKIP_RE.fullmatch(text) or (_SKIP_RE.search(text) and len(text) < 24):
        stored = answers.get(step) or "(skipped)"
    answers[step] = stored
    _store_answer(memory, step, stored)
    out["answers"] = answers
    out["brief_kh"] = stored != "(skipped)"
    out["last_brief"] = stored
    out["brief_step"] = step
    nxt = _next_missing(out)
    if nxt == "done":
        out["cycles"] = int(out.get("cycles") or 0) + 1
        out["answers"] = {}
        out["step"] = "ache"
    else:
        out["step"] = nxt
    return out


def format_learn_director(state: dict[str, Any], *, room: str = "lockee") -> str:
    if state.get("paused"):
        return (
            "\n\n[LOCKEE LEARN — paused]\n"
            "He asked to stop the questions. Stay in the tease. "
            "Do not grill him this turn.\n"
        )
    question = current_question(state)
    answers = state.get("answers") if isinstance(state.get("answers"), dict) else {}
    have = ", ".join(
        f"{k}={str(v)[:50]}" for k, v in answers.items() if str(v).strip()
    ) or "nothing this cycle"
    if room != "lockee":
        return ""
    return (
        "\n\n[LOCKEE LEARN — private with him]\n"
        f"Already this cycle: {have}\n"
        "Talk to HIM. Stay in the personality traits. Keep him aroused.\n"
        "Answer what he said first. Then ask ONLY this one question "
        "(do not dump a form):\n"
        f"{question}\n"
        "Store what he says. Never offer unlock. Never leak her private plan.\n"
    )


def format_kh_briefing(state: dict[str, Any], memory: Any | None = None) -> str:
    step = str(state.get("brief_step") or state.get("step") or "note")
    text = str(state.get("last_brief") or "").strip()
    if not text:
        return ""
    label = {
        "ache": "how desperate he is",
        "buttons": "what wrecks him",
        "fantasy": "a fantasy he has not admitted to you",
        "works": "what actually made him leak",
        "tasks": "tasks that keep him aching",
        "games": "games he would hate losing",
        "limits": "a limit update",
    }.get(step, "something useful")
    ideas = suggest_tasks_and_games(memory)
    extra = ""
    if ideas:
        extra = "\nI can use this. Next ideas: " + "; ".join(ideas[:2]) + "."
    return (
        f"Lockee intel (he cannot see this): he told me {label} — {text[:220]}."
        f"{extra}"
    )


def suggest_tasks_and_games(memory: Any | None = None) -> list[str]:
    kinks = [str(x).strip() for x in (getattr(memory, "kinks", None) or []) if str(x).strip()]
    works = [str(x).strip() for x in (getattr(memory, "what_works", None) or []) if str(x).strip()]
    tasks = [str(x).strip() for x in (getattr(memory, "learned_tasks", None) or []) if str(x).strip()]
    games = [str(x).strip() for x in (getattr(memory, "learned_games", None) or []) if str(x).strip()]
    ache = [str(x).strip() for x in (getattr(memory, "arousal_notes", None) or []) if str(x).strip()]
    flavour = (works[-1:] or kinks[-1:] or ache[-1:] or ["denial"]).pop()
    flavour = flavour.split(".")[0][:40]
    out: list[str] = []
    if tasks:
        out.append(f"Task: {tasks[-1][:80]}")
    else:
        out.append(f"Task: five-minute {flavour} tease, no touch, report how hard he is")
    if games:
        out.append(f"Game: {games[-1][:80]}")
    else:
        out.append(
            f"Game: he picks 1–4; each number is a {flavour} dare plus minutes added"
        )
    if kinks:
        out.append(f"Keep him aroused with {kinks[-1][:50]} — drip it, don't dump it")
    return out[:4]


def format_mentor_play_block(memory: Any | None = None) -> str:
    ideas = suggest_tasks_and_games(memory)
    intel = [str(x).strip() for x in (getattr(memory, "lockee_intel", None) or []) if str(x).strip()]
    lines = [
        "[MENTOR — help the keyholder keep him aroused]",
        "You are her assistant and mentor. Coach her. She holds the keys.",
        "Propose one task and one game from what you learned in his private chat.",
        "Do not dump a menu unless she asked for options. She approves; then run it.",
    ]
    if intel:
        lines.append("Latest lockee intel:")
        lines.extend(f"  • {n}" for n in intel[-6:])
    if ideas:
        lines.append("Ready to offer:")
        lines.extend(f"  • {n}" for n in ideas)
    return "\n".join(lines)
