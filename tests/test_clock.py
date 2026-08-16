import unittest

from app.clock import (
    asks_clock_time,
    asks_lock_remaining,
    format_clock_reply,
    format_local_now,
    local_now,
)


class ClockTests(unittest.TestCase):
    def test_detects_clock_not_lock(self) -> None:
        self.assertTrue(asks_clock_time("what time is it?"))
        self.assertTrue(asks_clock_time("no the actual time"))
        self.assertTrue(
            asks_clock_time("tell me the current time here in my timezone")
        )
        self.assertTrue(asks_clock_time("are you time aware"))
        self.assertFalse(asks_clock_time("hello"))
        self.assertFalse(asks_lock_remaining("what time is it?"))
        self.assertTrue(asks_lock_remaining("how long left on the lock"))
        self.assertTrue(asks_lock_remaining("what's his time looking like now"))
        self.assertTrue(asks_clock_time("what time is it") and not asks_lock_remaining(
            "what time is it"
        ))

    def test_formats_london_clock(self) -> None:
        stamp = format_local_now(tz_name="Europe/London")
        now = local_now(tz_name="Europe/London")
        self.assertIn("Europe/London", stamp)
        self.assertIn(now.strftime("%B"), stamp)
        self.assertRegex(stamp, r"\b\d{2}:\d{2}\b")

    def test_clock_reply_includes_time(self) -> None:
        sub = format_clock_reply(role="sub", tz_name="Europe/London")
        kh = format_clock_reply(role="domme", tz_name="Europe/London")
        self.assertIn("Europe/London", sub)
        self.assertIn("not how long", sub.lower())
        self.assertIn("Europe/London", kh)
        self.assertIn("wall clock", kh.lower())
        self.assertNotIn("hidden", sub.lower())
