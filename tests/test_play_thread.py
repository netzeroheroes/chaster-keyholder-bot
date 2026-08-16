import unittest

from app.play_thread import (
    apply_play_updates,
    box_button_message,
    format_play_block,
    parse_play_updates,
    wants_uncage_play,
)
from app.scene import SceneState


class PlayThreadTests(unittest.TestCase):
    def test_detects_uncage_and_edge(self) -> None:
        self.assertTrue(wants_uncage_play("maybe i should let him out for some teasing"))
        self.assertTrue(wants_uncage_play("i want to edge him"))
        self.assertTrue(wants_uncage_play("uncaged"))
        self.assertFalse(wants_uncage_play("what's his time looking like"))

    def test_thread_stays_on_uncage_not_tuesday(self) -> None:
        scene = SceneState()
        apply_play_updates(scene, parse_play_updates("ideas for a play session tonight"))
        apply_play_updates(scene, parse_play_updates("maybe i could edge him"))
        apply_play_updates(scene, parse_play_updates("uncaged"))
        text = format_play_block(scene)
        self.assertIn("UNCAGED", text)
        self.assertIn("edge him", text)
        self.assertIn("not a veto", text)
        self.assertIn("Never tell him to unlock himself", text)
        self.assertIn("do not reset", text.lower())

    def test_box_buttons_start_play_thread(self) -> None:
        unlock = box_button_message("unlock")
        lock = box_button_message("lock")
        self.assertIsNotNone(unlock)
        self.assertIsNotNone(lock)
        self.assertTrue(wants_uncage_play(unlock or ""))
        self.assertIn("tease him", (unlock or "").lower())
        self.assertIn("tease him", (lock or "").lower())
        self.assertEqual(parse_play_updates(lock or "").get("cage"), "on")
        self.assertIsNone(box_button_message("sync_time"))

    def test_keep_locked_can_override(self) -> None:
        scene = SceneState()
        apply_play_updates(scene, parse_play_updates("uncaged"))
        apply_play_updates(scene, parse_play_updates("keep him locked"))
        self.assertEqual(scene.play_thread.get("cage"), "on")


if __name__ == "__main__":
    unittest.main()
