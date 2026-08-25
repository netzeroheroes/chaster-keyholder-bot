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

_REMEMBER_CMD = re.compile(
    r"^\s*(?:please\s+)?(?:remember|note|save|store)\s+(?:that\s+|this\s+:?\s*)?(.+)$",
    re.I | re.DOTALL,
)
_FORGET_CMD = re.compile(
    r"^\s*(?:please\s+)?(?:forget|erase|delete)\s+(?:that\s+|this\s+|the\s+fact\s+)?:?\s*(.+)$",
    re.I | re.DOTALL,
)
_RECALL_CMD = re.compile(
    r"\b("
    r"what do you remember|what have you remembered|"
    r"recall(?:\s+what you know)?|show (?:me )?memory|"
    r"what do you know about (?:him|us|our|the sub)|"
    r"remind me what (?:we|you) (?:said|noted|remembered)"
    r")\b",
    re.I,
)
_SUB_NAME_RE = re.compile(
    r"\b(?:his name is|the lockee(?:'s name)? is|call the lockee)\s+"
    r"([A-Za-z][\w'-]{1,24})\b",
    re.I,
)
_TITLE_RE = re.compile(
    r"\bcall him\s+([A-Za-z][\w'-]{1,24})\b",
    re.I,
)
_HARD_LIMIT_RE = re.compile(
    r"\bhard limits?\s*[:\-]\s*([^.;\n]{3,80})",
    re.I,
)
_KINK_LINE_RE = re.compile(
    r"\b(?:his (?:kinks?|likes?)|he (?:likes|loves|gets off on))\s*[:\-]\s*([^.;\n]{3,80})",
    re.I,
)
_REMEMBER_INLINE = re.compile(
    r"\b(?:remember|note that|save that)\s+(?:that\s+)?(.{8,240})",
    re.I,
)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _merge_str_list(old: list[str] | None, new: list[str] | None, cap: int) -> list[str]:
    cur = [str(x).strip() for x in (old or []) if str(x).strip()]
    seen = {x.lower() for x in cur}
    for item in new or []:
        text = str(item).strip()
        if not text or text.lower() in seen:
            continue
        cur.append(text)
        seen.add(text.lower())
    return cur[-cap:]


@dataclass
class LongTermMemory:
    """Persistent facts that develop across sessions and can be recalled later."""

    domme_name: str = ""
    domme_title: str = ""  # optional honorific; prefer domme_name in chat
    bot_name: str = "Keyholder"  # AI Domme display name in chat
    sub_name: str = ""
    # From Chaster public profiles (sex / sexuality / pronouns)
    domme_gender: str = ""
    domme_sexuality: str = ""
    domme_pronouns: str = ""
    sub_gender: str = ""
    sub_sexuality: str = ""
    sub_pronouns: str = ""
    sub_titles: list[str] = field(default_factory=list)
    hard_limits: list[str] = field(default_factory=list)
    soft_limits: list[str] = field(default_factory=list)
    kinks: list[str] = field(default_factory=list)
    chastity: dict[str, str] = field(default_factory=dict)
    relationship_notes: list[str] = field(default_factory=list)
    timeline: list[str] = field(default_factory=list)  # dated developments
    private_bond: list[str] = field(default_factory=list)  # Domme↔bot friendship notes
    # Explicit durable facts Domme told us to keep ("remember that…")
    facts: list[str] = field(default_factory=list)
    # Real Chaster action log only (never invent)
    lock_log: list[str] = field(default_factory=list)
    # Keyholder pleasure — used to run the lock for HER
    her_turn_ons: list[str] = field(default_factory=list)
    her_fantasies: list[str] = field(default_factory=list)
    her_orgasms: list[dict] = field(default_factory=list)
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
        # Prefer real Domme name over stale generic honorific
        title = str(data.get("domme_title") or "").strip()
        if title.lower() in {"mistress", "miss"} and str(data.get("domme_name") or "").strip():
            data["domme_title"] = ""
        return cls(**data)

    def save(self, path: Path = MEMORY_PATH) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            payload = {
                "domme_name": self.domme_name,
                "domme_title": self.domme_title,
                "bot_name": self.bot_name or "Keyholder",
                "sub_name": self.sub_name,
                "domme_gender": self.domme_gender,
                "domme_sexuality": self.domme_sexuality,
                "domme_pronouns": self.domme_pronouns,
                "sub_gender": self.sub_gender,
                "sub_sexuality": self.sub_sexuality,
                "sub_pronouns": self.sub_pronouns,
                "sub_titles": list(self.sub_titles)[-40:],
                "hard_limits": list(self.hard_limits)[-40:],
                "soft_limits": list(self.soft_limits)[-40:],
                "kinks": list(self.kinks)[-60:],
                "chastity": dict(self.chastity),
                "relationship_notes": list(self.relationship_notes)[-80:],
                "timeline": list(self.timeline)[-120:],
                "private_bond": list(self.private_bond)[-80:],
                "facts": list(self.facts)[-100:],
                "lock_log": list(self.lock_log)[-80:],
                "her_turn_ons": list(self.her_turn_ons)[-40:],
                "her_fantasies": list(self.her_fantasies)[-40:],
                "her_orgasms": list(self.her_orgasms)[-40:],
            }
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "domme_name": self.domme_name,
                "domme_title": self.domme_title,
                "bot_name": self.bot_name or "Keyholder",
                "sub_name": self.sub_name,
                "domme_gender": self.domme_gender,
                "domme_sexuality": self.domme_sexuality,
                "domme_pronouns": self.domme_pronouns,
                "sub_gender": self.sub_gender,
                "sub_sexuality": self.sub_sexuality,
                "sub_pronouns": self.sub_pronouns,
                "sub_titles": list(self.sub_titles),
                "hard_limits": list(self.hard_limits),
                "soft_limits": list(self.soft_limits),
                "kinks": list(self.kinks),
                "chastity": dict(self.chastity),
                "relationship_notes": list(self.relationship_notes),
                "timeline": list(self.timeline),
                "private_bond": list(self.private_bond),
                "facts": list(self.facts),
                "lock_log": list(self.lock_log),
                "her_turn_ons": list(self.her_turn_ons),
                "her_fantasies": list(self.her_fantasies),
                "her_orgasms": list(self.her_orgasms),
            }

    def update_fields(self, **kwargs: object) -> dict:
        with self._lock:
            for key, value in kwargs.items():
                if key.startswith("_") or not hasattr(self, key):
                    continue
                setattr(self, key, value)
        self.save()
        return self.snapshot()

    def remember_fact(self, fact: str, *, source: str = "Domme") -> str:
        text = re.sub(r"\s+", " ", (fact or "").strip())
        if not text:
            return ""
        # Avoid duplicate near-identical facts
        entry = f"{_today()} [{source}] {text}"
        with self._lock:
            low = text.lower()
            self.facts = [
                f for f in self.facts if low not in f.lower() and f.lower() not in low
            ]
            self.facts.append(entry)
            self.facts = self.facts[-100:]
            self.timeline.append(f"{_today()} Remembered: {text[:160]}")
            self.timeline = self.timeline[-120:]
        self.save()
        return entry

    def forget_fact(self, query: str) -> list[str]:
        q = (query or "").strip().lower()
        if not q:
            return []
        removed: list[str] = []
        with self._lock:
            kept: list[str] = []
            for f in self.facts:
                if q in f.lower():
                    removed.append(f)
                else:
                    kept.append(f)
            self.facts = kept
        if removed:
            self.save()
        return removed

    def ingest_spoken_notes(self, message: str, *, speaker: str = "Domme") -> dict:
        """Cheap deterministic memory from keyholder chat — no LLM."""
        text = message or ""
        updates: dict[str, object] = {}
        name_m = _SUB_NAME_RE.search(text)
        if name_m and not (self.sub_name or "").strip():
            updates["sub_name"] = name_m.group(1).strip()
        title_m = _TITLE_RE.search(text)
        if title_m:
            updates["sub_titles"] = _merge_str_list(
                self.sub_titles, [title_m.group(1).strip()], 40
            )
        lim_m = _HARD_LIMIT_RE.search(text)
        if lim_m:
            bits = [p.strip() for p in re.split(r"\s*(?:,|;|/|\band\b)\s*", lim_m.group(1)) if p.strip()]
            if bits:
                updates["hard_limits"] = _merge_str_list(self.hard_limits, bits[:8], 40)
        kink_m = _KINK_LINE_RE.search(text)
        if kink_m:
            bits = [p.strip() for p in re.split(r"\s*(?:,|;|/|\band\b)\s*", kink_m.group(1)) if p.strip()]
            if bits:
                updates["kinks"] = _merge_str_list(self.kinks, bits[:8], 60)
        if not self.parse_remember_command(text):
            rem = _REMEMBER_INLINE.search(text)
            if rem:
                fact = rem.group(1).strip().strip("\"'")
                if len(fact) >= 8 and not re.search(
                    r"\b(add|remove|freeze|unfreeze|hide|show)\b.*\b(time|timer|lock)\b",
                    fact,
                    re.I,
                ):
                    self.remember_fact(fact, source=speaker)
        if updates:
            self.update_fields(**updates)
        return updates

    def log_lock_event(
        self,
        *,
        action: str,
        remaining: str = "",
        by: str = "",
        detail: str = "",
    ) -> None:
        bits = [b for b in (action, detail) if b]
        line = f"{_now_stamp()} — {'; '.join(bits)}"
        if remaining:
            line += f" · remaining {remaining}"
        if by:
            line += f" · by {by}"
        with self._lock:
            self.lock_log.append(line)
            self.lock_log = self.lock_log[-80:]
            if remaining:
                self.chastity["last_remaining"] = remaining
                self.chastity["last_lock_event"] = line
                self.chastity["updated_at"] = _now_stamp()
        self.save()

    def prompt_block(self, *, room: str) -> str:
        from app.roles import domme_address

        snap = self.snapshot()
        address = domme_address(self)
        domme = snap["domme_name"] or "the Domme"
        sub = snap["sub_name"] or "the Sub"
        title = (snap.get("domme_title") or "").strip()
        title_bit = f" (optional title: {title})" if title else ""
        if room == "group":
            return self._group_memory_block(snap)

        def _demo(prefix: str) -> str:
            bits = [
                b
                for b in (
                    snap.get(f"{prefix}_gender") or "",
                    snap.get(f"{prefix}_sexuality") or "",
                    snap.get(f"{prefix}_pronouns") or "",
                )
                if b and str(b).lower() not in {"unspecified", "not-specified", ""}
            ]
            return ", ".join(str(b) for b in bits) if bits else "(not on profile yet)"

        from app.bot_persona import identity_lines

        you_line, frame_line = identity_lines(
            bot_name=str(snap.get("bot_name") or "Keyholder")
        )
        lines = [
            "LONG-TERM MEMORY (persistent — recall these when asked; treat as true):",
            "PEOPLE (never mix these up):",
            you_line,
            f"- Human Domme / keyholder = {domme}{title_bit}. "
            "In GROUP chat address her as 'keyholder' (UI shows who spoke — no usernames, "
            "no [Keyholder: Domme] labels). In PRIVATE you may use her name.",
            f"- Human Domme profile: {_demo('domme')}.",
            f"- Human Sub / lockee = {sub}. Titles: {', '.join(snap['sub_titles']) or '(none yet)'}.",
            f"- Human Sub profile: {_demo('sub')}.",
            "- In GROUP, address the wearer as 'lockee' (not his username).",
            "- Begging is to ease/stop punishments — never demand he beg to unlock.",
            frame_line,
            "- CHASTER TRUTH (STRICT): Never invent lock remaining time, totals, or keypad codes.",
            "  Live numbers come ONLY from [CHASTER LIVE STATUS] / ACTION DONE this turn.",
            "  Memory chastity/lock_log are for context/recall — not a substitute for live status.",
            f"- Hard limits: {', '.join(snap['hard_limits']) or '(ask / learn)'}.",
            f"- Soft limits: {', '.join(snap['soft_limits']) or '(none noted)'}.",
            f"- Kinks (his): {', '.join(snap['kinks']) or '(discovering)'}.",
            f"- Chastity notes: {json.dumps(snap['chastity'], ensure_ascii=False) if snap['chastity'] else '(unknown)'}.",
        ]
        from app.her_taste import format_her_taste_block

        her = format_her_taste_block(self, room=room)
        if her:
            lines.append(her)
        if snap["facts"]:
            lines.append("- Durable facts to RECALL when relevant or when asked:")
            lines.extend(f"  • {n}" for n in snap["facts"][-20:])
        if snap["lock_log"]:
            lines.append("- Recent REAL lock actions (API-confirmed history):")
            lines.extend(f"  • {n}" for n in snap["lock_log"][-10:])
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
            f"ALWAYS acknowledge {address} when she speaks — reply to her, include her, "
            "never ignore her in favor of only the Sub."
        )
        lines.append(
            "When Domme says 'remember that…', store it. When she asks what you remember, "
            "quote facts/timeline/lock_log accurately — do not invent."
        )
        return "\n".join(lines)

    @staticmethod
    def _group_memory_block(snap: dict) -> str:
        """Short facts only — a long memory essay makes Group sound like a briefing."""
        bot = snap.get("bot_name") or "Keyholder"
        domme = snap.get("domme_name") or "the keyholder"
        sub = snap.get("sub_name") or "the lockee"
        from app.bot_persona import persona_from_controls

        spec = persona_from_controls()
        if spec["sex"] == "male" or spec["persona"] in {"bull", "male_dom"}:
            who = (
                f"You are {bot}, a man. She ({domme}) is his girlfriend and the keyholder. "
                f"He ({sub}) is the lockee. You may play with her while he stays locked."
            )
        else:
            who = (
                f"You are {bot}. She ({domme}) is his girlfriend and the keyholder. "
                f"He ({sub}) is the lockee. You talked her into locking him."
            )
        lines = [
            who,
            f"Limits: {', '.join(snap['hard_limits']) or 'ask / learn'}.",
            f"Kinks: {', '.join(snap['kinks']) or 'discovering'}.",
        ]
        ons = [str(x) for x in (snap.get("her_turn_ons") or []) if str(x).strip()]
        if ons:
            lines.append("Her turn-ons (use on him, do not list): " + ", ".join(ons[-6:]))
        fan = [str(x) for x in (snap.get("her_fantasies") or []) if str(x).strip()]
        if fan:
            lines.append(
                "Her fantasies (use on him, do not list): " + ", ".join(fan[-4:])
            )
        last = (snap.get("her_orgasms") or [])[-1:] if snap.get("her_orgasms") else []
        if last and isinstance(last[0], dict) and last[0].get("rating"):
            if last[0].get("tell_him") in (True, "true", "1"):
                lines.append(
                    f"She last logged an orgasm at {last[0].get('rating')}/10 — "
                    "he did not. Tease that."
                )
            else:
                lines.append(
                    "She came recently. He did not get the score. "
                    "Tease that she came. Do not quote her rating."
                )
        if snap.get("chastity"):
            lines.append(
                "Cage notes: "
                + json.dumps(snap["chastity"], ensure_ascii=False)
            )
        if snap.get("facts"):
            lines.append("Facts: " + "; ".join(snap["facts"][-10:]))
        return "\n".join(lines)

    def format_recall_reply(self, *, for_domme: bool = True) -> str:
        from app.roles import domme_address

        snap = self.snapshot()
        title = domme_address(self)
        lines = [
            f"{title} — here's what I'm holding onto:" if for_domme else "What I know about you:",
        ]
        if snap["facts"]:
            lines.append("Facts:")
            lines.extend(f"• {n}" for n in snap["facts"][-15:])
        else:
            lines.append("Facts: (none stored yet — tell me 'remember that…')")
        if snap["lock_log"]:
            lines.append("Recent real lock actions:")
            lines.extend(f"• {n}" for n in snap["lock_log"][-8:])
        if snap["timeline"]:
            lines.append("Timeline:")
            lines.extend(f"• {n}" for n in snap["timeline"][-8:])
        if for_domme and snap["private_bond"]:
            lines.append("Private bond notes:")
            lines.extend(f"• {n}" for n in snap["private_bond"][-6:])
        if snap["hard_limits"] or snap["kinks"]:
            lines.append(
                f"Limits/kinks: hard={', '.join(snap['hard_limits']) or '—'}; "
                f"kinks={', '.join(snap['kinks']) or '—'}"
            )
        return "\n".join(lines)

    @staticmethod
    def parse_remember_command(message: str) -> str | None:
        m = _REMEMBER_CMD.match((message or "").strip())
        if not m:
            return None
        fact = m.group(1).strip().strip("\"'")
        if len(fact) < 3:
            return None
        # Don't treat lock orders as remember commands
        if re.search(r"\b(add|remove|freeze|unfreeze|hide|show)\b.*\b(time|timer|lock)\b", fact, re.I):
            return None
        return fact

    @staticmethod
    def parse_forget_command(message: str) -> str | None:
        m = _FORGET_CMD.match((message or "").strip())
        if not m:
            return None
        q = m.group(1).strip().strip("\"'")
        return q if len(q) >= 2 else None

    @staticmethod
    def wants_recall(message: str) -> bool:
        return bool(_RECALL_CMD.search(message or ""))

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
        today = _today()
        current = json.dumps(self.snapshot(), ensure_ascii=False)
        system = (
            "You maintain long-term memory for an adult D/s chastity game (18+ only).\n"
            "Given the latest turn, update MEMORY as JSON ONLY (no markdown).\n"
            "Keep prior facts unless corrected. Append short new notes.\n"
            "Schema keys: domme_name, domme_title, bot_name, sub_name, "
            "domme_gender, domme_sexuality, domme_pronouns, "
            "sub_gender, sub_sexuality, sub_pronouns, sub_titles, "
            "hard_limits, soft_limits, kinks, chastity (object of string values), "
            "relationship_notes, timeline, private_bond, facts, lock_log, "
            "her_turn_ons, her_fantasies.\n"
            "Prefer keeping domme_name as her Chaster username; do NOT force title 'Mistress'.\n"
            "IMPORTANT:\n"
            "- facts = durable preferences/rules Domme wants remembered (short bullets).\n"
            "- lock_log = ONLY copy real API-confirmed lock actions already present; "
            "never invent lock durations or new lock_log lines from fiction.\n"
            "- Do not put invented remaining times into chastity.\n"
            "- Keep chastity.last_orgasm / cage / lock_goal_days if already set.\n"
            "Lists of strings. timeline/private_bond/facts should preferably start with the date.\n"
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
        if isinstance(data.get("domme_name"), str) and data["domme_name"].strip():
            updates["domme_name"] = data["domme_name"].strip()
        if isinstance(data.get("domme_title"), str) and data["domme_title"].strip():
            updates["domme_title"] = data["domme_title"].strip()
        if isinstance(data.get("bot_name"), str) and data["bot_name"].strip():
            updates["bot_name"] = data["bot_name"].strip()
        if isinstance(data.get("sub_name"), str) and data["sub_name"].strip():
            updates["sub_name"] = data["sub_name"].strip()
        for key in (
            "domme_gender",
            "domme_sexuality",
            "domme_pronouns",
            "sub_gender",
            "sub_sexuality",
            "sub_pronouns",
        ):
            if isinstance(data.get(key), str) and data[key].strip():
                updates[key] = data[key].strip()
        for key, cap in (
            ("sub_titles", 40),
            ("hard_limits", 40),
            ("soft_limits", 40),
            ("kinks", 60),
            ("relationship_notes", 80),
            ("timeline", 120),
            ("private_bond", 80),
            ("facts", 100),
            ("her_turn_ons", 40),
            ("her_fantasies", 40),
        ):
            incoming = _str_list(data.get(key)) if key in data else []
            if incoming:
                updates[key] = _merge_str_list(getattr(self, key), incoming, cap)
        if isinstance(data.get("chastity"), dict):
            # Don't let model invent remaining-time fields
            ch = {
                str(k): str(v)
                for k, v in data["chastity"].items()
                if str(v).strip()
                and not re.search(r"remaining|end_date|seconds", str(k), re.I)
            }
            # Keep our authoritative lock fields
            with self._lock:
                for keep in (
                    "last_remaining",
                    "last_lock_event",
                    "updated_at",
                    "last_orgasm",
                    "cage",
                    "lock_goal_days",
                ):
                    if keep in self.chastity:
                        ch[keep] = self.chastity[keep]
            updates["chastity"] = ch
        # lock_log is append-only from real API — never replace from LLM fiction
        if updates:
            self.update_fields(**updates)
            log.info("Memory updated from %s/%s turn", room, speaker)
