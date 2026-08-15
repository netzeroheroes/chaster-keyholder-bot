import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import hygiene_request as hr


class HygieneRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "hygiene_request.json"
        self.patcher = patch.object(hr, "PATH", self.path)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_request_approve_unlock_relock(self) -> None:
        asked = hr.request_hygiene(allowed_seconds=300)
        self.assertEqual(asked["status"], "requested")
        approved = hr.approve_hygiene(allowed_seconds=300)
        self.assertEqual(approved["status"], "approved")
        opened = hr.mark_unlocked(allowed_seconds=300)
        self.assertEqual(opened["status"], "unlocked")
        self.assertFalse(opened["late"])
        self.assertGreater(opened["remaining_seconds"], 0)
        closed = hr.mark_relocked()
        self.assertEqual(closed["status"], "idle")

    def test_cannot_unlock_before_approve(self) -> None:
        hr.request_hygiene(allowed_seconds=120)
        with self.assertRaises(ValueError):
            hr.mark_unlocked(allowed_seconds=120)

    def test_late_needs_punish(self) -> None:
        hr.request_hygiene(allowed_seconds=60)
        hr.approve_hygiene(allowed_seconds=60)
        hr.mark_unlocked(allowed_seconds=60)
        past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        with hr._lock:
            raw = hr._load_raw()
            raw["deadline_at"] = past
            hr._save_raw(raw)
        self.assertTrue(hr.should_punish())
        hr.mark_punished()
        self.assertFalse(hr.should_punish())

    def test_deny_allows_new_request(self) -> None:
        hr.request_hygiene(allowed_seconds=120)
        cleared = hr.deny_hygiene()
        self.assertEqual(cleared["status"], "denied")
        again = hr.request_hygiene(allowed_seconds=180)
        self.assertEqual(again["status"], "requested")

    def test_reset_clears_stuck_request(self) -> None:
        hr.request_hygiene(allowed_seconds=120)
        cleared = hr.reset_hygiene()
        self.assertEqual(cleared["status"], "idle")
        again = hr.request_hygiene(allowed_seconds=120)
        self.assertEqual(again["status"], "requested")

    def test_chat_duration_approves(self) -> None:
        self.assertEqual(hr.parse_kh_hygiene_reply("15mins"), ("approve", 900))
        self.assertEqual(hr.parse_kh_hygiene_reply("15 mins"), ("approve", 900))
        self.assertEqual(hr.parse_kh_hygiene_reply("15"), ("approve", 900))
        self.assertEqual(hr.parse_kh_hygiene_reply("no"), ("deny", 0))
        self.assertIsNone(hr.parse_kh_hygiene_reply("add 15 minutes to his lock"))

    def test_unlock_uses_approved_timescale(self) -> None:
        hr.request_hygiene(allowed_seconds=600)
        hr.approve_hygiene(allowed_seconds=180)
        opened = hr.mark_unlocked(allowed_seconds=0)
        self.assertEqual(opened["allowed_seconds"], 180)


if __name__ == "__main__":
    unittest.main()
