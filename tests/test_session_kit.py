import unittest

from app.session_kit import (
    asked_kit_focus,
    format_kit_choice_block,
    kit_lists_for_choice,
    parse_named_kit_pick,
    wants_kit_choice,
)
from app.speaker_guard import should_take_to_private


class KitChoiceTests(unittest.TestCase):
    def test_detects_which_toy_and_choose_one(self) -> None:
        self.assertTrue(
            wants_kit_choice("so wich of his toys should we use on him today")
        )
        self.assertTrue(wants_kit_choice("choose one"))
        self.assertTrue(
            wants_kit_choice(
                "which of his kinks are we going to use against him tonight"
            )
        )
        self.assertFalse(wants_kit_choice("what's his time looking like"))
        self.assertFalse(wants_kit_choice("list his kinks"))

    def test_focus_follows_the_question(self) -> None:
        self.assertEqual(
            asked_kit_focus("which of his toys should we use"),
            "toys",
        )
        self.assertEqual(
            asked_kit_focus("which of his kinks tonight"),
            "kinks",
        )
        self.assertEqual(asked_kit_focus("choose one"), "both")

    def test_prefers_ticked_kit_over_fallback_catalog(self) -> None:
        kinks, toys, source = kit_lists_for_choice(
            session_kinks=["Cuckolding"],
            session_toys=["Humbler"],
            memory_kinks=["sph"],
            catalog={
                "source": "fallback",
                "kinks": [{"name": "Wax play", "rating": "love"}],
                "toys": [{"name": "Flogger"}],
            },
        )
        self.assertEqual(kinks, ["Cuckolding"])
        self.assertEqual(toys, ["Humbler"])
        self.assertEqual(source, "kit")

    def test_uses_profile_when_kit_empty(self) -> None:
        kinks, toys, source = kit_lists_for_choice(
            session_kinks=[],
            session_toys=[],
            memory_kinks=["old note"],
            catalog={
                "source": "chaster",
                "kinks": [
                    {"name": "Cuckolding", "rating": "love"},
                    {"name": "Humiliation", "rating": "like"},
                ],
                "toys": [{"name": "Nipple clamps"}, {"name": "Plug"}],
            },
        )
        self.assertEqual(kinks, ["Cuckolding", "Humiliation"])
        self.assertIn("Plug", toys)
        self.assertEqual(source, "profile")

    def test_ignores_fallback_toys_as_his(self) -> None:
        kinks, toys, source = kit_lists_for_choice(
            session_kinks=[],
            session_toys=[],
            memory_kinks=["Humiliation"],
            catalog={
                "source": "fallback",
                "kinks": [{"name": "Wax play", "rating": "love"}],
                "toys": [{"name": "Flogger"}],
            },
        )
        self.assertEqual(kinks, ["Humiliation"])
        self.assertEqual(toys, [])
        self.assertEqual(source, "memory")

    def test_director_forbids_the_one_that(self) -> None:
        text = format_kit_choice_block(
            kinks=["Cuckolding"],
            toys=["Humbler"],
            focus="toys",
            source="kit",
        )
        self.assertIn("Humbler", text)
        self.assertNotIn("Cuckolding", text)
        self.assertIn("the one that makes him squirm", text)
        self.assertIn("NAME the item", text)

    def test_parses_named_pick(self) -> None:
        bits = parse_named_kit_pick(
            "use the humbler on him",
            kinks=["Cuckolding"],
            toys=["Humbler", "Plug"],
        )
        self.assertEqual(bits.get("toy"), "Humbler")

    def test_group_kit_ask_leaves_for_private(self) -> None:
        self.assertTrue(
            should_take_to_private("which of his toys should we use on him")
        )


class TogetherKitTests(unittest.TestCase):
    def test_together_unless_virtual(self) -> None:
        from app.session_kit import format_together_director, physical_together

        self.assertTrue(physical_together(""))
        self.assertTrue(physical_together("in_person"))
        self.assertFalse(physical_together("virtual"))
        director = format_together_director(
            room="group",
            session_mode="",
            toy="Humbler",
            kink="Cuckolding",
        )
        self.assertIn("Humbler", director)
        self.assertIn("Cuckolding", director)
        self.assertIn("when she is free", director.lower())
        remote = format_together_director(
            room="group", session_mode="virtual", toy="Humbler"
        )
        self.assertIn("VIRTUAL", remote)

    def test_pick_varies_with_salt(self) -> None:
        from app.session_kit import pick_kit_props

        a = pick_kit_props(
            session_kinks=["Edging", "Humiliation"],
            session_toys=["Plug", "Crop", "Gag"],
            salt="alpha",
        )
        b = pick_kit_props(
            session_kinks=["Edging", "Humiliation"],
            session_toys=["Plug", "Crop", "Gag"],
            salt="omega",
        )
        self.assertTrue(a[0] or a[1])
        self.assertIn(a[0], {"Plug", "Crop", "Gag"})
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
