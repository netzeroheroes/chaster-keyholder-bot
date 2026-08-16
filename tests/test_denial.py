import unittest
from datetime import date
from types import SimpleNamespace

from app.denial import (
    days_since_orgasm,
    format_denial_block,
    format_seasonal_block,
    parse_denial_updates,
    parse_kink_limit_updates,
    wants_intake,
    wants_persona,
)


class DenialTests(unittest.TestCase):
    def test_intake_phrases(self) -> None:
        self.assertTrue(wants_intake("interview him"))
        self.assertTrue(wants_intake("ask about his cage"))
        self.assertTrue(wants_intake("tell me your kinks and limits"))
        self.assertFalse(wants_intake("double it"))
        self.assertTrue(wants_persona("please tell me about your persona"))
        self.assertFalse(wants_persona("double it"))

    def test_parses_kinks_and_hard_limits(self) -> None:
        bits = parse_kink_limit_updates(
            "I like humiliation and bondage. Hard limits: blood, public exposure"
        )
        self.assertIn("humiliation", [x.lower() for x in bits["kinks"]])
        self.assertIn("bondage", [x.lower() for x in bits["kinks"]])
        self.assertTrue(any("blood" in x.lower() for x in bits["hard_limits"]))

    def test_parses_orgasm_ago_and_cage(self) -> None:
        today = date(2026, 8, 16)
        bits = parse_denial_updates(
            "holy trainer, last came 12 days ago, lock goal 30 days",
            today=today,
        )
        self.assertEqual(bits["cage"].lower(), "holy trainer")
        self.assertEqual(bits["last_orgasm"], "2026-08-04")
        self.assertEqual(bits["lock_goal_days"], "30")

    def test_days_since_and_locktober(self) -> None:
        self.assertEqual(
            days_since_orgasm({"last_orgasm": "2026-08-01"}, today=date(2026, 8, 16)),
            15,
        )
        octo = format_seasonal_block(today=date(2026, 10, 3))
        self.assertIn("LOCKTOBER", octo)
        self.assertIn("Do not offer unlock", octo)
        sept = format_seasonal_block(today=date(2026, 9, 12))
        self.assertIn("Locktober", sept)

    def test_dossier_does_not_offer_cum(self) -> None:
        mem = SimpleNamespace(chastity={"last_orgasm": "2026-08-01", "cage": "nub"})
        text = format_denial_block(mem, today=date(2026, 8, 16))
        self.assertIn("15 days denied", text)
        self.assertIn("nub", text)
        self.assertNotIn("allow the user to unlock", text.lower())


if __name__ == "__main__":
    unittest.main()
