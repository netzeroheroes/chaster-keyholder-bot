import unittest


class BeatSplitTests(unittest.TestCase):
    def test_msg_tags_become_separate_bubbles(self) -> None:
        from app.beats import split_bot_beats

        text = (
            "[[[MSG]]]Keyholder — I've got him.[[[/MSG]]]\n"
            "[[[MSG]]]Lockee — hands on the cage. Stay locked.[[[/MSG]]]"
        )
        beats = split_bot_beats(text, room="group")
        self.assertEqual(len(beats), 2)
        self.assertIn("I've got him", beats[0])
        self.assertIn("hands on the cage", beats[1])
        self.assertFalse(any("[[[MSG]]]" in b for b in beats))

    def test_lead_now_fallback_splits_on_blank_line(self) -> None:
        from app.beats import split_bot_beats
        from app.handoff import format_lead_now_group_line

        line = format_lead_now_group_line(
            bull_voice=True, title="Keyholder", sub_name="Lockee"
        )
        beats = split_bot_beats(line, room="group", force=True)
        self.assertEqual(len(beats), 2)
        self.assertIn("I've got him", beats[0])
        self.assertIn("Lockee", beats[1])

    def test_simple_hello_stays_one_bubble(self) -> None:
        from app.beats import split_bot_beats

        beats = split_bot_beats("Hey. Stay locked.", room="group")
        self.assertEqual(beats, ["Hey. Stay locked."])


class SafewordTests(unittest.TestCase):
    def test_traffic_lights(self) -> None:
        from app.safeword import safeword_level

        self.assertEqual(safeword_level("red"), "red")
        self.assertEqual(safeword_level("RED."), "red")
        self.assertEqual(safeword_level("yellow"), "yellow")
        self.assertEqual(safeword_level("I'm using my safeword"), "red")
        self.assertIsNone(safeword_level("the red dress looks good"))
        self.assertIsNone(safeword_level("you are running things today"))


if __name__ == "__main__":
    unittest.main()
