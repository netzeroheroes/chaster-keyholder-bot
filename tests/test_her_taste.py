import unittest
from types import SimpleNamespace

from app.her_taste import (
    apply_her_taste,
    format_learn_her_director,
    format_orgasm_director,
    parse_her_taste,
    parse_orgasm_rating,
    record_orgasm,
    wants_her_taste,
)


class _Mem:
    def __init__(self) -> None:
        self.her_turn_ons: list[str] = []
        self.her_fantasies: list[str] = []
        self.her_orgasms: list[dict] = []

    def update_fields(self, **kwargs: object) -> dict:
        for key, value in kwargs.items():
            setattr(self, key, value)
        return {}


class HerTasteTests(unittest.TestCase):
    def test_parses_rating_line(self) -> None:
        self.assertEqual(
            parse_orgasm_rating("I came. Orgasm rating 8/10. Note: cuck talk"),
            8,
        )
        self.assertEqual(parse_orgasm_rating("orgasm rating: 10"), 10)
        self.assertIsNone(parse_orgasm_rating("hello"))

    def test_parses_turn_ons_and_fantasies(self) -> None:
        bits = parse_her_taste(
            "Turns me on: him begging, locked leaking. "
            "My fantasy: bull nights while he listens."
        )
        self.assertIn("him begging", bits["her_turn_ons"])
        self.assertTrue(any("bull" in x.lower() for x in bits["her_fantasies"]))

    def test_learn_me_trigger(self) -> None:
        self.assertTrue(
            wants_her_taste(
                "Ask me what turns me on. Learn my fantasies so you can use the lock for my pleasure."
            )
        )
        self.assertIn("Ask one thing", format_learn_her_director(room="private"))

    def test_records_and_directs(self) -> None:
        mem = _Mem()
        apply_her_taste(mem, {"her_turn_ons": ["cuck talk"]})
        self.assertEqual(mem.her_turn_ons, ["cuck talk"])
        record_orgasm(mem, 9, note="the denial")
        self.assertEqual(mem.her_orgasms[-1]["rating"], "9")
        self.assertFalse(mem.her_orgasms[-1]["tell_him"])
        record_orgasm(mem, 8, note="told", tell_him=True)
        self.assertTrue(mem.her_orgasms[-1]["tell_him"])
        high = format_orgasm_director(9, note="the denial", room="group")
        self.assertIn("HIGH", high)
        self.assertIn("he waits", high.lower())
        low = format_orgasm_director(2, room="private")
        self.assertIn("LOW", low)
        self.assertIn("Do not punish her", low)

    def test_private_orgasm_notice_hides_score(self) -> None:
        from app.her_taste import format_orgasm_lockee_notice

        line = format_orgasm_lockee_notice(bull_voice=True)
        self.assertIn("She just came", line)
        self.assertIn("I was with her", line)
        self.assertNotIn("/10", line)
        self.assertNotIn("rating", line.lower())

    def test_memory_prompt_includes_her_pleasure(self) -> None:
        from app.memory import LongTermMemory

        mem = LongTermMemory()
        mem.her_turn_ons = ["him locked while I come"]
        mem.her_fantasies = ["bull night"]
        mem.her_orgasms = [{"when": "now", "rating": "8", "note": "cuck talk"}]
        block = mem.prompt_block(room="private")
        self.assertIn("him locked while I come", block)
        self.assertIn("bull night", block)
        self.assertIn("8/10", block)
        group = mem._group_memory_block(mem.snapshot())
        self.assertIn("turn-ons", group.lower())
        self.assertIn("she came", group.lower())
        self.assertNotIn("8/10", group)

    def test_ingest_and_merge_does_not_wipe(self) -> None:
        from app.memory import LongTermMemory, _merge_str_list

        mem = LongTermMemory()
        mem.save = lambda path=None: None  # type: ignore[method-assign]
        mem.kinks = ["denial"]
        mem.hard_limits = ["scat"]
        mem.ingest_spoken_notes(
            "His name is Alex. Hard limits: blood. He likes: teasing, cuckold. "
            "Remember that he begs at night.",
            speaker="Domme",
        )
        self.assertEqual(mem.sub_name, "Alex")
        self.assertIn("blood", mem.hard_limits)
        self.assertIn("teasing", mem.kinks)
        self.assertTrue(any("begs" in f.lower() for f in mem.facts))
        merged = _merge_str_list(["denial"], ["denial", "cuckold"], 60)
        self.assertEqual(merged, ["denial", "cuckold"])


if __name__ == "__main__":
    unittest.main()
