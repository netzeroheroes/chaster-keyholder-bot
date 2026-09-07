import unittest

from app.lockee_learn import (
    apply_learn_answer,
    current_question,
    format_kh_briefing,
    format_learn_director,
    format_mentor_play_block,
    start_learn,
    suggest_tasks_and_games,
    wants_cancel_learn,
)
from app.memory import LongTermMemory
from app.personality_traits import (
    format_traits_block,
    normalize_traits,
    traits_csv,
)
from app.roles import (
    LOCKEE_PRIVATE_HARD_RULE,
    access_denied_detail,
    can_access,
    format_user_line,
    speaker_label,
)


class TraitTests(unittest.TestCase):
    def test_default_is_bratty_tease(self) -> None:
        self.assertEqual(normalize_traits(""), ["bratty", "tease"])
        self.assertEqual(normalize_traits(None), ["bratty", "tease"])
        self.assertEqual(traits_csv("Bratty, TEASE, mean girl"), "bratty, tease, mean girl")

    def test_unknown_tokens_kept(self) -> None:
        self.assertIn("dry humour", normalize_traits("dry humour, bratty"))

    def test_traits_block_mentors_her(self) -> None:
        from app import runtime_controls as rc

        ctrl = rc.RuntimeControls()
        rc._CONTROLS = ctrl
        self.addCleanup(lambda: setattr(rc, "_CONTROLS", None))
        ctrl.bot_traits = "bratty, tease"
        private = format_traits_block(room="private")
        self.assertIn("bratty", private)
        self.assertIn("mentor the keyholder", private.lower())
        lockee = format_traits_block(room="lockee")
        self.assertIn("on HIM", lockee)


class RoomAccessTests(unittest.TestCase):
    def test_each_role_has_own_private(self) -> None:
        self.assertTrue(can_access("domme", "private"))
        self.assertFalse(can_access("sub", "private"))
        self.assertTrue(can_access("sub", "lockee"))
        self.assertFalse(can_access("domme", "lockee"))
        self.assertTrue(can_access("sub", "group"))
        self.assertIn("keyholder", access_denied_detail("sub", "private").lower())
        self.assertIn("lockee", access_denied_detail("domme", "lockee").lower())

    def test_lockee_private_line(self) -> None:
        label = speaker_label("sub", chaster_username="Chastityguy80", room="lockee")
        self.assertTrue(label.startswith("Lockee"))
        line = format_user_line(
            "sub",
            "humiliation wrecks me",
            chaster_username="Chastityguy80",
            room="lockee",
        )
        self.assertIn(LOCKEE_PRIVATE_HARD_RULE[:20], line)
        self.assertIn("human lockee", line.lower())
        self.assertIn("humiliation wrecks me", line)


class LockeeLearnTests(unittest.TestCase):
    def test_stores_and_briefs(self) -> None:
        mem = LongTermMemory()
        mem.save = lambda path=None: None  # type: ignore[method-assign]
        state = start_learn()
        self.assertIn("desperate", current_question(state).lower())
        state = apply_learn_answer(state, "I'm a 9. SPH wrecks me.", memory=mem)
        self.assertTrue(state["brief_kh"])
        self.assertIn("SPH wrecks me", " ".join(mem.arousal_notes))
        self.assertTrue(mem.lockee_intel)
        brief = format_kh_briefing(state, mem)
        self.assertIn("Lockee intel", brief)
        self.assertIn("SPH", brief)

    def test_skips_hello(self) -> None:
        mem = LongTermMemory()
        mem.save = lambda path=None: None  # type: ignore[method-assign]
        state = apply_learn_answer(start_learn(), "hey", memory=mem)
        self.assertFalse(state["brief_kh"])
        self.assertEqual(state["step"], "ache")
        self.assertFalse(mem.arousal_notes)

    def test_cancel_pauses(self) -> None:
        self.assertTrue(wants_cancel_learn("stop asking questions"))
        state = apply_learn_answer(start_learn(), "enough questions")
        self.assertTrue(state["paused"])
        director = format_learn_director(state, room="lockee")
        self.assertIn("paused", director.lower())

    def test_suggests_from_kinks(self) -> None:
        mem = LongTermMemory(kinks=["humiliation"])
        ideas = suggest_tasks_and_games(mem)
        self.assertTrue(ideas)
        self.assertTrue(any("humiliation" in x.lower() or "Task" in x for x in ideas))
        block = format_mentor_play_block(mem)
        self.assertIn("assistant and mentor", block.lower())
        self.assertIn("Ready to offer", block)


class MentorPersonaTests(unittest.TestCase):
    def test_default_is_mentor(self) -> None:
        from app.bot_persona import DEFAULT_PERSONA, format_persona_block, normalize_persona

        self.assertEqual(DEFAULT_PERSONA, "mentor")
        self.assertEqual(normalize_persona("assistant"), "mentor")
        from app import runtime_controls as rc

        ctrl = rc.RuntimeControls()
        rc._CONTROLS = ctrl
        self.addCleanup(lambda: setattr(rc, "_CONTROLS", None))
        ctrl.bot_persona = "mentor"
        text = format_persona_block(room="private")
        self.assertIn("assistant and mentor", text.lower())
        self.assertIn("tasks and games", text.lower())

    def test_male_sex_promotes_mentor_to_bull(self) -> None:
        from app import runtime_controls as rc

        ctrl = rc.RuntimeControls()
        ctrl.save = lambda: None  # type: ignore[method-assign]
        self.assertEqual(ctrl.bot_persona, "mentor")
        ctrl.update(bot_sex="male")
        self.assertEqual(ctrl.bot_persona, "bull")
        ctrl.update(bot_persona="mentor", bot_sex="male")
        self.assertEqual(ctrl.bot_persona, "mentor")

    def test_controls_normalize_traits(self) -> None:
        from app import runtime_controls as rc

        ctrl = rc.RuntimeControls()
        ctrl.save = lambda: None  # type: ignore[method-assign]
        ctrl.update(bot_traits="Bratty, TEASE")
        self.assertEqual(ctrl.bot_traits, "bratty, tease")


class SceneLockeePromptTests(unittest.TestCase):
    def test_lockee_channel(self) -> None:
        from app.scene import SceneState

        body = SceneState().system_prompt_for("lockee")
        self.assertIn("LOCKEE PRIVATE", body)
        self.assertIn("Never unlock", body)
        kh = SceneState().system_prompt_for("private")
        self.assertIn("assistant and mentor", kh.lower())


if __name__ == "__main__":
    unittest.main()
