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
from app.chat_service import _clean_history_for_model, extract_spoken_user
from app.roles import (
    GROUP_KEYHOLDER_RULE,
    PRIVATE_HARD_RULE,
    format_user_line,
    history_speaker_tag,
    is_bot_display_speaker,
    speaker_label,
)
from app.speaker_guard import (
    enforce_private_keyholder_voice,
    mistreats_domme_as_sub,
    refers_to_keyholder_as_she,
    rewrite_keyholder_as_you,
    should_take_to_private,
    talks_to_lockee,
    wants_private_chat,
)


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
        self.assertFalse(is_bot_display_speaker("Lockee (@Chastityguy80)"))

    def test_group_labels_are_keyholder_and_lockee(self) -> None:
        kh = speaker_label("domme", chaster_username="TheBosses", room="group")
        lockee = speaker_label("sub", chaster_username="Chastityguy80", room="group")
        self.assertTrue(kh.startswith("Keyholder"))
        self.assertTrue(lockee.startswith("Lockee"))
        line = format_user_line(
            "domme",
            "i might unlock him for a bit tonight to play",
            chaster_username="TheBosses",
            room="group",
        )
        self.assertIn("KEYHOLDER", line.upper())
        self.assertIn(GROUP_KEYHOLDER_RULE[:20], line)
        self.assertIn("human keyholder", line.lower())

    def test_history_keeps_role_tags(self) -> None:
        blob = format_user_line(
            "domme",
            "i might unlock him for a bit tonight to play",
            chaster_username="TheBosses",
            room="group",
        )
        self.assertEqual(history_speaker_tag(blob), "Keyholder (@TheBosses)")
        self.assertEqual(
            extract_spoken_user(blob),
            "i might unlock him for a bit tonight to play",
        )
        cleaned = _clean_history_for_model(
            [
                {"role": "user", "content": blob},
                {"role": "assistant", "content": "Nice — take him out tonight."},
            ],
            room="group",
        )
        self.assertTrue(cleaned[0]["content"].startswith("Keyholder (@TheBosses):"))
        self.assertTrue(cleaned[1]["content"].startswith("Bot:"))

    def test_she_lets_him_out_becomes_you(self) -> None:
        raw = (
            "Great! I have some ideas on how we can tease and torment him "
            "even more before she lets him out."
        )
        self.assertTrue(refers_to_keyholder_as_she(raw))
        fixed = rewrite_keyholder_as_you(raw)
        self.assertIn("before you let him out", fixed)
        self.assertNotIn("she lets", fixed.lower())
        self.assertEqual(
            rewrite_keyholder_as_you("She has the keys."),
            "you have the keys.",
        )

    def test_group_kh_reply_must_not_talk_to_him(self) -> None:
        bad = (
            "Oh, so you think she'll just hand you freedom so easily? "
            "Maybe I should tell her how badly you're begging."
        )
        self.assertTrue(mistreats_domme_as_sub(bad))
        self.assertTrue(
            talks_to_lockee("Patience, pet, the cage waits for no one.")
        )
        self.assertTrue(
            talks_to_lockee("You'll earn your release, but not a moment sooner.")
        )

    def test_private_ask_leaves_group(self) -> None:
        self.assertTrue(
            wants_private_chat(
                "maybe you should message me in private and we can discuss it"
            )
        )
        self.assertTrue(
            should_take_to_private(
                "i might unlock him for a bit tonight what should i do with him"
            )
        )
        self.assertFalse(should_take_to_private("tell him he's staying locked"))
        self.assertTrue(
            should_take_to_private(
                "so he's going to get unlocked for 1 hr tonight what should we do to him"
            )
        )
        self.assertTrue(should_take_to_private("what should we do with him"))

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

    def test_bull_private_keeps_heat_toward_her(self) -> None:
        from app.speaker_guard import repair_domme_misaddress

        flirt = (
            "Come here. He's locked. I want you tonight while he waits."
        )
        self.assertFalse(
            mistreats_domme_as_sub(
                flirt,
                user_message="i think i need some attention",
                bull_voice=True,
            )
        )
        kept = enforce_private_keyholder_voice(
            flirt, fallback="spin ideas", bull_voice=True
        )
        self.assertEqual(kept, flirt)
        self.assertNotIn(
            "spin ideas",
            repair_domme_misaddress(
                domme_title="TheBosses",
                sub_name="him",
                original_topic="i think i need some attention",
                bull_voice=True,
            ).lower(),
        )

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
