import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import play_session as ps
from app.play_thread import format_play_block, parse_play_updates
from app.scene import SceneState


class PlaySessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "play_session.json"
        self.patcher = patch.object(ps, "PATH", self.path)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_parses_two_minutes_per_minute(self) -> None:
        self.assertEqual(ps.parse_play_rate("2 minutes per minute"), 2.0)
        self.assertEqual(ps.parse_play_rate("2 min locked per min out"), 2.0)
        self.assertEqual(ps.parse_play_rate("3x"), 3.0)
        self.assertEqual(ps.parse_play_rate("2:1"), 2.0)
        self.assertEqual(ps.parse_play_rate("double time"), 2.0)
        self.assertEqual(ps.parse_play_rate("yes time it"), 2.0)
        self.assertEqual(ps.parse_play_rate("no extra time"), 0.0)
        self.assertIsNone(ps.parse_play_rate("double it"))
        self.assertIsNone(ps.parse_play_rate("i think he deserves an hour tonight"))

    def test_an_hour_outside_tonight(self) -> None:
        bits = parse_play_updates(
            "i think he deserves an hour outside of it tonight"
        )
        self.assertEqual(bits.get("session"), "tonight")
        self.assertEqual(bits.get("cage"), "off_for_play")
        self.assertEqual(bits.get("window"), "1 hour")

    def test_hour_plus_rate_keeps_window(self) -> None:
        bits = parse_play_updates(
            "he's getting 1 hr tonight, 2 minutes per minute"
        )
        self.assertIn("1", bits.get("window") or "")
        self.assertEqual(bits.get("debt_rate"), "2")

    def test_rate_does_not_become_the_window(self) -> None:
        bits = parse_play_updates("2 minutes per minute")
        self.assertEqual(bits.get("debt_rate"), "2")
        self.assertNotIn("window", bits)

    def test_unlock_lock_applies_two_x(self) -> None:
        ps.set_rate(2.0)
        opened = ps.start_on_unlock()
        self.assertEqual(opened["status"], "running")
        past = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        with ps._lock:
            raw = ps._load_raw()
            raw["unlocked_at"] = past
            ps._save_raw(raw)
        settled = ps.settle_on_lock()
        self.assertIsNotNone(settled)
        assert settled is not None
        self.assertGreaterEqual(settled["out_seconds"], 3500)
        self.assertEqual(settled["add_seconds"], int(round(settled["out_seconds"] * 2)))
        self.assertEqual(settled["status"], "idle")

    def test_no_rate_does_not_add(self) -> None:
        ps.start_on_unlock()
        past = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
        with ps._lock:
            raw = ps._load_raw()
            raw["unlocked_at"] = past
            ps._save_raw(raw)
        settled = ps.settle_on_lock()
        self.assertIsNotNone(settled)
        assert settled is not None
        self.assertGreater(settled["out_seconds"], 0)
        self.assertEqual(settled["add_seconds"], 0)

    def test_scene_card_forbids_one_to_one(self) -> None:
        scene = SceneState()
        from app.play_thread import apply_play_updates

        apply_play_updates(scene, parse_play_updates("unlock him for 1 hr tonight"))
        text = format_play_block(scene)
        self.assertIn("2 min locked per min out", text)
        self.assertIn("not a price", text.lower())
        self.assertNotIn("1 minute added per minute out — that is a price", text)

    def test_director_waits_for_yes(self) -> None:
        text = ps.format_play_session_block()
        self.assertIn("2 min locked per min out", text)
        self.assertIn("Wait for her yes", text)
        self.assertIn("1 minute added per minute out", text)


if __name__ == "__main__":
    unittest.main()
