import unittest

from app.chaster_actions import (
    ChasterActionResult,
    format_scale_reply,
    format_spoken_duration,
    parse_chaster_intent,
    parse_scale_command,
    seconds_for_scale,
)
from app.clock import asks_lock_remaining
from app.roles import (
    PRIVATE_HARD_RULE,
    format_user_line,
    is_bot_display_speaker,
    speaker_label,
)
from app.speaker_guard import enforce_private_keyholder_voice, talks_to_lockee


class PrivateKeyholderTests(unittest.TestCase):
    def test_private_human_is_keyholder(self) -> None:
        label = speaker_label(
            "domme", chaster_username="TheBosses", room="private"
        )
        self.assertTrue(label.startswith("Keyholder"))
        self.assertIn("TheBosses", label)
        self.assertFalse(is_bot_display_speaker(label))

    def test_bot_name_keyholder_is_bot(self) -> None:
        self.assertTrue(is_bot_display_speaker("Keyholder"))
        self.assertTrue(is_bot_display_speaker("Keyholder", "Keyholder"))
        self.assertFalse(is_bot_display_speaker("Domme (@TheBosses)"))
        self.assertFalse(is_bot_display_speaker("Keyholder (@TheBosses)"))

    def test_private_user_line_hard_rule(self) -> None:
        line = format_user_line(
            "domme",
            "what's his time looking like now",
            chaster_username="TheBosses",
            room="private",
        )
        self.assertIn(PRIVATE_HARD_RULE.split(":")[0], line)
        self.assertIn("keyholder", line.lower())
        self.assertNotIn("wearer (lockee)", line)

    def test_his_time_is_lock_status(self) -> None:
        intent = parse_chaster_intent("what's his time looking like now")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.kind, "status")
        self.assertIsNone(parse_chaster_intent("what time is it?"))

    def test_hows_his_lock_is_status(self) -> None:
        self.assertTrue(asks_lock_remaining("hows his lock"))
        self.assertTrue(asks_lock_remaining("how's his lock"))
        intent = parse_chaster_intent("hows his lock")
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.kind, "status")

    def test_earn_it_line_is_lockee_voice(self) -> None:
        line = (
            "Maybe if you earn it. Stay with that ache — "
            "I'll talk to her about what comes next."
        )
        self.assertTrue(talks_to_lockee(line))
        fixed = enforce_private_keyholder_voice(
            line, fallback="His lock remaining is 5 days."
        )
        self.assertEqual(fixed, "His lock remaining is 5 days.")
        self.assertNotIn("earn it", fixed.lower())
        self.assertNotIn("sub", fixed.lower())

    def test_double_it_adds_remaining(self) -> None:
        intent = parse_chaster_intent("double it", remaining_seconds=3600)
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.kind, "add_time")
        self.assertEqual(intent.seconds, 3600)
        self.assertEqual(intent.reason, "double")
        self.assertIsNone(parse_chaster_intent("double it"))

    def test_scale_command_words(self) -> None:
        self.assertEqual(parse_scale_command("double it"), "double")
        self.assertEqual(parse_scale_command("triple it"), "triple")
        self.assertEqual(parse_scale_command("halve it"), "halve")
        self.assertEqual(parse_scale_command("please double his lock time"), "double")
        self.assertIsNone(parse_scale_command("hows his lock"))
        self.assertIsNone(parse_scale_command("double the tease"))

    def test_seconds_for_scale_is_true_double(self) -> None:
        rem = 6 * 86400 + 5 * 3600 + 18 * 60
        self.assertEqual(seconds_for_scale("double", rem), rem)
        self.assertEqual(seconds_for_scale("triple", rem), rem * 2)
        self.assertEqual(seconds_for_scale("halve", rem), -(rem // 2))
        doubled = rem + seconds_for_scale("double", rem)
        self.assertEqual(format_spoken_duration(doubled), "12 days, 10 hours, and 36 minutes")
        self.assertEqual(
            format_spoken_duration(rem), "6 days, 5 hours, and 18 minutes"
        )

    def test_scale_reply_uses_real_before_after(self) -> None:
        rem = 6 * 86400 + 5 * 3600 + 7 * 60
        doubled = rem * 2
        result = ChasterActionResult(
            ok=True,
            facts="",
            before={"remaining_seconds": rem},
            lock={"remaining_seconds": doubled},
        )
        reply = format_scale_reply("double", result)
        self.assertIn("doubled", reply)
        self.assertIn("6 days, 5 hours, and 7 minutes", reply)
        self.assertIn("12 days, 10 hours, and 14 minutes", reply)
        self.assertNotIn("10 days", reply)
        self.assertNotIn("GROUP", reply)


if __name__ == "__main__":
    unittest.main()
