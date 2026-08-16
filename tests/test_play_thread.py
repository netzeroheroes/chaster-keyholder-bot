import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import play_session as ps
from app.play_thread import (
    apply_play_updates,
    box_button_message,
    format_play_block,
    parse_play_updates,
    wants_uncage_play,
)
from app.scene import SceneState


class PlayThreadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.patcher = patch.object(
            ps, "PATH", Path(self.tmp.name) / "play_session.json"
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

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
        self.assertIn("long lock, not tonight's game", text)
        self.assertIn("Never tell him to unlock himself", text)
        self.assertIn("do not start a new scene", text.lower())

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

    def test_scene_card_keeps_tonight_and_flavors(self) -> None:
        scene = SceneState()
        apply_play_updates(
            scene,
            parse_play_updates(
                "i might unlock him for a bit tonight what should i do with him"
            ),
        )
        apply_play_updates(
            scene,
            parse_play_updates("i want to incorporate a bit of humiliation into it"),
        )
        apply_play_updates(
            scene,
            parse_play_updates("the pathetic thing has a bit of a cuck fetish"),
        )
        text = format_play_block(scene)
        self.assertIn("tonight", text.lower())
        self.assertIn("UNCAGED", text)
        self.assertIn("humiliation", text.lower())
        self.assertIn("cuck", text.lower())
        self.assertIn("SCENE WE ARE ORGANISING", text)
        self.assertIn("Lock him at the END", text)
        self.assertIn("PLAY time", text)
        self.assertIn("Do NOT make the Chaster timer", text)

    def test_parses_one_hour_unlock_tonight(self) -> None:
        bits = parse_play_updates(
            "so he's going to get unlocked for 1 hr tonight what should we do to him"
        )
        self.assertEqual(bits.get("session"), "tonight")
        self.assertEqual(bits.get("cage"), "off_for_play")
        self.assertIn("1", bits.get("window") or "")
        tease = parse_play_updates("should i tease him whilst he's uncaged")
        self.assertEqual(tease.get("tease"), "yes")

    def test_keep_locked_can_override(self) -> None:
        scene = SceneState()
        apply_play_updates(scene, parse_play_updates("uncaged"))
        apply_play_updates(scene, parse_play_updates("keep him locked"))
        self.assertEqual(scene.play_thread.get("cage"), "on")


if __name__ == "__main__":
    unittest.main()
