import unittest

from planner import (
    DEFAULT_MINUTES,
    OPENER,
    compose_chat_reply,
    compose_itinerary,
    extract_json,
    kit_block,
    sanitize_brief,
    sanitize_session,
    scene_markdown,
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
        play = " ".join(f"{s['title']} {s['phase']}" for s in scene["steps"]).lower()
        self.assertNotIn("aftercare", play)
        md = scene_markdown(scene).lower()
        before, sep, after = md.partition("aftercare")
        self.assertTrue(sep)
        self.assertIn("after the clock", after)
        self.assertIn("minutes of play", before)
        self.assertNotIn("aftercare", before)


class JsonTests(unittest.TestCase):
    def test_unwraps_fences(self) -> None:
        data = extract_json('Sure.\n```json\n{"title": "Held"}\n```\n')
        self.assertEqual(data and data.get("title"), "Held")


class SurpriseTests(unittest.TestCase):
    def test_has_kinks(self) -> None:
        self.assertGreaterEqual(len(surprise_brief()["kinks"]), 3)


class ChatTests(unittest.TestCase):
    def test_opener_asks_for_toys_and_hard_limits(self) -> None:
        lower = OPENER.lower()
        self.assertIn("toys", lower)
        self.assertIn("hard limits", lower)
        self.assertIn("bdsm scenario", lower)

    def test_instructions_match_planner_persona(self) -> None:
        from pathlib import Path

        text = Path(__file__).resolve().parents[1].joinpath("instructions.md").read_text(
            encoding="utf-8"
        ).lower()
        self.assertIn("scenario:", text)
        self.assertIn("dominant (d)", text)
        self.assertIn("climax & aftercare", text)
        self.assertIn("no blood", text)
        self.assertIn("female dominant", text)

    def test_fallback_uses_named_toys(self) -> None:
        reply = compose_chat_reply("flogger paddle cane cuffs collar")
        lower = reply.lower()
        self.assertIn("theme:", lower)
        self.assertIn("flogger", lower)
        self.assertIn("female dominant", lower)

    def test_banned_follow_up(self) -> None:
        with self.assertRaises(ValueError):
            _clean_messages([{"role": "user", "content": "write a teen scene"}])


class KitTests(unittest.TestCase):
    def test_kit_block_uses_toys_kinks_limits_and_duration(self) -> None:
        text = kit_block(
            {
                "toys": "collar, cage",
                "kinks": ["chastity", "humiliation"],
                "limits": "blood",
            },
            {"duration_minutes": 45, "focus": "ownership", "orgasm": "denied"},
        )
        lower = text.lower()
        self.assertIn("collar", lower)
        self.assertIn("chastity", lower)
        self.assertIn("blood", lower)
        self.assertIn("45 minutes", lower)
        self.assertNotIn("30 minutes", lower)
        self.assertIn("climax & aftercare", lower)
        self.assertIn("inside the clock", lower)

    def test_session_duration_is_not_locked_to_example(self) -> None:
        self.assertEqual(sanitize_session({"duration_minutes": 90})["duration_minutes"], 90)
        self.assertEqual(sanitize_session({})["duration_minutes"], DEFAULT_MINUTES)


if __name__ == "__main__":
    unittest.main()
