"""Read what they meant — not a keyword checklist."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

KINDS = frozenset(
    {
        "act_on_him",
        "lead",
        "talk_to_her",
        "plan",
        "status",
        "aftercare",
        "reply",
    }
)

_CLASSIFY_SYSTEM = """You classify INTENT in a 3-person chastity chat.
People: keyholder (his girlfriend, she/her), lockee (locked, he/him), you (AI co-keyholder / bull).

Return ONLY JSON:
{"kind":"act_on_him|lead|talk_to_her|plan|status|aftercare|reply","to":"him"|"her","escalate":true|false}

kind meaning (read the message — typos and slang count; do not require specific words):
- act_on_him: she wants HIM treated / teased / used / made more desperate. An order for the scene, not a chat with her.
- lead: she is handing you control of the scene.
- talk_to_her: she is talking to YOU about herself or the two of you.
- plan: she wants ideas or a scheme he should not read.
- status: she is asking about his lock / remaining time.
- aftercare: the scene should soften or stop.
- reply: ordinary chat.

to = who you should address as "you" this turn.
escalate = she wants more intensity on the current beat with him.

If she comments on how he is being treated, that is act_on_him even if she never said "lead" or "control"."""


@dataclass
class TurnIntent:
    kind: str = "reply"
    to: str = "her"
    escalate: bool = False
    source: str = "default"

    @property
    def run_him(self) -> bool:
        return self.kind in {"act_on_him", "lead"} or self.escalate


def parse_intent_json(raw: str) -> TurnIntent:
    text = (raw or "").strip()
    if not text:
        return TurnIntent()
    match = re.search(r"\{[^{}]*\}", text, re.S)
    if not match:
        return TurnIntent()
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return TurnIntent()
    if not isinstance(data, dict):
        return TurnIntent()
    kind = str(data.get("kind") or data.get("intent") or "reply").strip().lower()
    if kind not in KINDS:
        kind = "reply"
    to = str(data.get("to") or "").strip().lower()
    if to not in {"him", "her"}:
        to = "him" if kind in {"act_on_him", "lead"} else "her"
    raw_esc = data.get("escalate")
    if isinstance(raw_esc, str):
        escalate = raw_esc.strip().lower() in {"1", "true", "yes"}
    else:
        escalate = bool(raw_esc)
    if kind == "act_on_him":
        to = "him"
    return TurnIntent(kind=kind, to=to, escalate=escalate, source="llm")


def _history_snippet(history: list[Any], *, limit: int = 6) -> str:
    lines: list[str] = []
    for msg in list(history or [])[-limit:]:
        role = str((msg or {}).get("role") or "")
        content = str((msg or {}).get("content") or "").strip()
        if not content:
            continue
        tag = "Bot" if role == "assistant" else "Human"
        lines.append(f"{tag}: {content[:280]}")
    return "\n".join(lines)


def intent_director(turn: TurnIntent, *, room: str = "") -> str:
    if turn.kind == "act_on_him" or turn.escalate:
        if (room or "") == "private":
            return (
                "[INTENT: She wants HIM treated. Answer her here, then [[[GROUP]]] "
                "the beat at him. Do not interview.]"
            )
        return (
            "[INTENT: She is steering how HE is treated. That is an order. "
            "Ack her in half a sentence, then talk TO him as you and do it. "
            "Do not bounce it back to her. Do not narrate that she's already got him.]"
        )
    if turn.kind == "lead":
        return (
            "[INTENT: She handed you the lead. Start. Do not interview her.]"
        )
    if turn.kind == "talk_to_her":
        return (
            "[INTENT: She is talking to YOU. Reply TO her. Him is he/him.]"
        )
    if turn.kind == "plan":
        return (
            "[INTENT: Planning — he should not read the scheme.]"
        )
    if turn.kind == "aftercare":
        return (
            "[INTENT: Soften. Aftercare. No pile-on tease.]"
        )
    if turn.kind == "status":
        return (
            "[INTENT: She asked about his lock. Quote live status plainly.]"
        )
    return (
        "[INTENT: Read THEY SAID for meaning, not keyword phrases. "
        "If she is steering him, act on him. If she is talking to you, answer her.]"
    )


async def classify_turn_intent(
    agent: Any,
    *,
    message: str,
    room: str,
    history: list[Any] | None = None,
) -> TurnIntent:
    said = (message or "").strip()
    if not said:
        return TurnIntent()
    key = str(getattr(getattr(agent, "settings", None), "llm_api_key", "") or "")
    if not key.strip():
        return TurnIntent()
    recent = _history_snippet(history or [])
    user = (
        f"Room: {room}\n"
        f"Recent:\n{recent or '(none)'}\n\n"
        f"Keyholder said:\n\"\"\"{said[:500]}\"\"\""
    )
    try:
        raw = await asyncio.wait_for(
            agent.complete_short(
                user,
                system_prompt=_CLASSIFY_SYSTEM,
                max_tokens=80,
                temperature=0.0,
            ),
            timeout=4.0,
        )
    except Exception:  # noqa: BLE001
        log.warning("Intent classify failed", exc_info=True)
        return TurnIntent()
    parsed = parse_intent_json(raw)
    if parsed.source != "llm":
        return TurnIntent()
    log.info(
        "Turn intent kind=%s to=%s escalate=%s",
        parsed.kind,
        parsed.to,
        parsed.escalate,
    )
    return parsed
