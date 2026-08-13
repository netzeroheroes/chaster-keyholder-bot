from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.agent import ChatAgent

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MEMORY_PATH = DATA_DIR / "memory.json"


@dataclass
class LongTermMemory:
    """Persistent facts that develop across sessions."""

    domme_name: str = ""
    domme_title: str = "Mistress"  # how bot addresses the Domme
    bot_name: str = "Keyholder"  # AI Domme display name in chat
    sub_name: str = ""
    sub_titles: list[str] = field(default_factory=list)
    hard_limits: list[str] = field(default_factory=list)
    soft_limits: list[str] = field(default_factory=list)
    kinks: list[str] = field(default_factory=list)
    chastity: dict[str, str] = field(default_factory=dict)
    relationship_notes: list[str] = field(default_factory=list)
    timeline: list[str] = field(default_factory=list)  # dated developments
    private_bond: list[str] = field(default_factory=list)  # Domme↔bot friendship notes
    _lock: Lock = field(default_factory=Lock, repr=False)

    @classmethod
    def load(cls, path: Path = MEMORY_PATH) -> LongTermMemory:
        if not path.is_file():
            mem = cls()
            mem.save(path)
            return mem
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.exception("Failed to load memory; starting fresh")
            return cls()
        known = {f.name for f in cls.__dataclass_fields__.values() if not f.name.startswith("_")}
        data = {k: v for k, v in raw.items() if k in known}
        return cls(**data)

    def save(self, path: Path = MEMORY_PATH) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            payload = {
                "domme_name": self.domme_name,
                "domme_title": self.domme_title,
                "bot_name": self.bot_name or "Keyholder",
                "sub_name": self.sub_name,
                "sub_titles": list(self.sub_titles),
                "hard_limits": list(self.hard_limits),
                "soft_limits": list(self.soft_limits),
                "kinks": list(self.kinks),
                "chastity": dict(self.chastity),
                "relationship_notes": list(self.relationship_notes)[-80:],
                "timeline": list(self.timeline)[-120:],
                "private_bond": list(self.private_bond)[-80:],
            }
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "domme_name": self.domme_name,
                "domme_title": self.domme_title,
                "bot_name": self.bot_name or "Keyholder",
                "sub_name": self.sub_name,
                "sub_titles": list(self.sub_titles),
                "hard_limits": list(self.hard_limits),
                "soft_limits": list(self.soft_limits),
                "kinks": list(self.kinks),
                "chastity": dict(self.chastity),
                "relationship_notes": list(self.relationship_notes),
                "timeline": list(self.timeline),
                "private_bond": list(self.private_bond),
            }

    def update_fields(self, **kwargs: object) -> dict:
        with self._lock:
            for key, value in kwargs.items():
                if key.startswith("_") or not hasattr(self, key):
                    continue
                setattr(self, key, value)
        self.save()
        return self.snapshot()

    def prompt_block(self, *, room: str) -> str:
        snap = self.snapshot()
        title = snap["domme_title"] or "Mistress"
        domme = snap["domme_name"] or "the Domme"
        sub = snap["sub_name"] or "the Sub"

        lines = [
            "LONG-TERM MEMORY (develops over time — treat as true):",
            "PEOPLE (never mix these up):",
            f"- You = AI Domme / keyholder named '{snap.get('bot_name') or 'Keyholder'}' (not the human Domme).",
            f"- Human Domme = {domme}. Address her as '{title}' (and by name when natural).",
            f"- Human Sub = {sub}. Titles: {', '.join(snap['sub_titles']) or '(none yet)'}.",
            "- CHASTER TRUTH: Never claim you changed a Chaster lock (time, freeze, hide timer, "
            "notes, notifications) unless this turn includes a CHASTER ACTION DONE/BLOCKED block.",
            f"- Hard limits: {', '.join(snap['hard_limits']) or '(ask / learn)'}.",
            f"- Soft limits: {', '.join(snap['soft_limits']) or '(none noted)'}.",
            f"- Kinks: {', '.join(snap['kinks']) or '(discovering)'}.",
            f"- Chastity: {json.dumps(snap['chastity'], ensure_ascii=False) if snap['chastity'] else '(unknown)'}.",
        ]
        if snap["relationship_notes"]:
            lines.append("- Relationship notes:")
            lines.extend(f"  • {n}" for n in snap["relationship_notes"][-12:])
        if snap["timeline"]:
            lines.append("- Timeline / development:")
            lines.extend(f"  • {n}" for n in snap["timeline"][-14:])
        if room == "private" and snap["private_bond"]:
            lines.append("- Bond with Domme (private):")
            lines.extend(f"  • {n}" for n in snap["private_bond"][-10:])

        lines.append(
            f"ALWAYS acknowledge {title} when she speaks — reply to her, include her, "
            "never ignore her in favor of only the Sub."
        )
        return "\n".join(lines)

    async def consolidate_from_turn(
        self,
        agent: ChatAgent,
        *,
        room: str,
        speaker: str,
        user_text: str,
        bot_text: str,
    ) -> None:
        """Extract durable facts from a turn and merge into memory."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        current = json.dumps(self.snapshot(), ensure_ascii=False)
        system = (
            "You maintain long-term memory for an adult D/s chastity game (18+ only).\n"
            "Given the latest turn, update MEMORY as JSON ONLY (no markdown).\n"
            "Keep prior facts unless corrected. Append short new timeline/private_bond notes.\n"
            "Schema keys: domme_name, domme_title, sub_name, sub_titles, hard_limits, "
            "soft_limits, kinks, chastity (object of string values), relationship_notes, "
            "timeline, private_bond.\n"
            "Lists of strings. chastity examples: status, cage, last_lock, typical_lock_days.\n"
            "timeline/private_bond entries should be short and preferably start with the date.\n"
            "If nothing new, return the current memory unchanged.\n"
            f"Today's date: {today}"
        )
        user = (
            f"ROOM: {room}\nSPEAKER: {speaker}\n"
            f"USER MESSAGE:\n{user_text}\n\nBOT REPLY:\n{bot_text}\n\n"
            f"CURRENT MEMORY JSON:\n{current}\n\n"
            "Return the full updated MEMORY JSON."
        )
        try:
            raw, _ = await agent.reply(user, history=[], system_prompt=system)
        except Exception:
            log.exception("Memory consolidation LLM call failed")
            return

        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Memory consolidation returned non-JSON; skipped")
            return

        if not isinstance(data, dict):
            return

        def _str_list(value: object) -> list[str]:
            if not isinstance(value, list):
                return []
            return [str(x).strip() for x in value if str(x).strip()]

        updates: dict[str, object] = {}
        if isinstance(data.get("domme_name"), str):
            updates["domme_name"] = data["domme_name"].strip()
        if isinstance(data.get("domme_title"), str) and data["domme_title"].strip():
            updates["domme_title"] = data["domme_title"].strip()
        if isinstance(data.get("sub_name"), str):
            updates["sub_name"] = data["sub_name"].strip()
        for key in ("sub_titles", "hard_limits", "soft_limits", "kinks"):
            if key in data:
                updates[key] = _str_list(data.get(key))
        if isinstance(data.get("chastity"), dict):
            updates["chastity"] = {
                str(k): str(v) for k, v in data["chastity"].items() if str(v).strip()
            }
        for key in ("relationship_notes", "timeline", "private_bond"):
            if key in data:
                updates[key] = _str_list(data.get(key))[-120:]

        if updates:
            self.update_fields(**updates)
            log.info("Memory updated from %s/%s turn", room, speaker)
