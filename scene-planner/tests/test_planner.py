import unittest

from planner import (
    OPENER,
    compose_chat_reply,
    compose_itinerary,
    extract_json,
    sanitize_brief,
    surprise_brief,
)
from planner import _clean_messages


class SanitizeTests(unittest.TestCase):
    def test_rejects_minor_content(self) -> None:
        with self.assertRaises(ValueError):
            sanitize_brief({"notes": "teen scene"})

    def test_clamps_duration(self) -> None:
        brief = sanitize_brief({"duration_minutes": 9999, "kinks": ["humiliation"]})
        self.assertEqual(brief["duration_minutes"], 480)


class ComposeTests(unittest.TestCase):
    def test_omits_limited_kink_and_covers_time(self) -> None:
        brief = sanitize_brief(
            {
                "duration_minutes": 60,
                "intensity": "extreme",
                "kinks": ["impact", "CBT", "chastity"],
                "limits": "CBT, impact",
            }
        )
        scene = compose_itinerary(brief)
        blob = " ".join(f"{s['title']} {s['domme']}" for s in scene["steps"]).lower()
        self.assertNotIn("cbt", blob)
        self.assertGreaterEqual(len(scene["steps"]), 4)
        self.assertEqual(scene["steps"][-1]["end_min"], 60)
        self.assertTrue(scene["aftercare"])


class JsonTests(unittest.TestCase):
    def test_unwraps_fences(self) -> None:
        data = extract_json('Sure.\n```json\n{"title": "Held"}\n```\n')
        self.assertEqual(data and data.get("title"), "Held")


class SurpriseTests(unittest.TestCase):
    def test_has_kinks(self) -> None:
        self.assertGreaterEqual(len(surprise_brief()["kinks"]), 3)


class ChatTests(unittest.TestCase):
    def test_opener_asks_for_toys_and_limits(self) -> None:
        lower = OPENER.lower()
        self.assertIn("toys", lower)
        self.assertIn("hard limits", lower)

    def test_fallback_uses_named_toys(self) -> None:
        reply = compose_chat_reply("flogger paddle cane cuffs collar")
        lower = reply.lower()
        self.assertIn("theme:", lower)
        self.assertIn("flogger", lower)
        self.assertIn("female dominant", lower)

    def test_banned_follow_up(self) -> None:
        with self.assertRaises(ValueError):
            _clean_messages([{"role": "user", "content": "write a teen scene"}])


if __name__ == "__main__":
    unittest.main()
