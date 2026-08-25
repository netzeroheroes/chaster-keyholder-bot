import unittest

from app.bot_persona import (
    default_sex_for,
    format_persona_block,
    normalize_persona,
    resolve_persona,
)
from app.kink_probe import (
    apply_probe_answer,
    current_question,
    format_probe_director,
    start_probe,
    wants_cancel_probe,
    wants_kink_probe,
    wants_probe_go,
)
from app.tease_play import (
    current_genre,
    format_game_director,
    format_porn_director,
    genre_query,
    pick_local_games,
    search_url,
    wants_game,
    wants_online_ideas,
    wants_porn,
)


class BotPersonaTests(unittest.TestCase):
    def test_bull_defaults_male(self) -> None:
        spec = resolve_persona(persona="bull")
        self.assertEqual(spec["persona"], "bull")
        self.assertEqual(spec["sex"], "male")
        self.assertEqual(spec["subject"], "he")
        self.assertEqual(default_sex_for("friend"), "female")
        self.assertEqual(normalize_persona("hotwife"), "bull")

    def test_sex_override_stays(self) -> None:
        spec = resolve_persona(persona="friend", sex="male")
        self.assertEqual(spec["persona"], "friend")
        self.assertEqual(spec["sex"], "male")

    def test_persona_block_beats_female_default(self) -> None:
        from app import runtime_controls as rc

        ctrl = rc.RuntimeControls()
        rc._CONTROLS = ctrl
        self.addCleanup(lambda: setattr(rc, "_CONTROLS", None))
        ctrl.bot_persona = "bull"
        ctrl.bot_sex = "male"
        text = format_persona_block(room="group")
        self.assertIn("BULL", text)
        self.assertIn("he/him", text)
        self.assertIn("You are a MAN", text)
        self.assertNotIn("best friend and co-keyholder", text)

    def test_male_sex_alone_enables_cuck_voice(self) -> None:
        from app.bot_persona import identity_lines
        from app import runtime_controls as rc

        ctrl = rc.RuntimeControls()
        rc._CONTROLS = ctrl
        self.addCleanup(lambda: setattr(rc, "_CONTROLS", None))
        ctrl.bot_persona = "friend"
        ctrl.bot_sex = "male"
        text = format_persona_block(room="group")
        self.assertIn("HARD IDENTITY: you are male", text)
        self.assertIn("CUCK / BULL", text)
        self.assertIn("You are a MAN", text)
        self.assertNotIn("wicked woman", text)
        you, frame = identity_lines(bot_name="Rex")
        self.assertIn("MAN", you)
        self.assertIn("cuckold", frame.lower())
        voice = rc.format_voice_block(room="group")
        self.assertIn("Male voice", voice)
        self.assertIn("She's with me tonight", voice)
        self.assertNotIn("talked her into locking that pathetic thing", voice)

    def test_group_voice_uses_bull_sample(self) -> None:
        from app import runtime_controls as rc

        ctrl = rc.RuntimeControls()
        rc._CONTROLS = ctrl
        self.addCleanup(lambda: setattr(rc, "_CONTROLS", None))
        ctrl.bot_persona = "bull"
        ctrl.bot_voice_sample = ""
        text = rc.format_voice_block(room="group")
        self.assertIn("Male voice", text)
        self.assertIn("She's with me tonight", text)
        self.assertNotIn("talked her into locking that pathetic thing", text)


class KinkProbeTests(unittest.TestCase):
    def test_start_phrases(self) -> None:
        self.assertTrue(wants_kink_probe("interview him"))
        self.assertTrue(wants_kink_probe("grill him about his kinks"))
        self.assertTrue(wants_kink_probe("tools to use against him"))
        self.assertTrue(wants_probe_go("do it now"))
        self.assertTrue(wants_cancel_probe("stop interviewing him"))
        self.assertFalse(wants_kink_probe("double the time"))

    def test_advances_and_stores(self) -> None:
        from types import SimpleNamespace

        mem = SimpleNamespace(kinks=[], hard_limits=[], soft_limits=[], update_fields=lambda **kw: None)
        stored: dict = {}

        def update_fields(**kwargs: object) -> None:
            stored.update(kwargs)
            for key, value in kwargs.items():
                setattr(mem, key, value)

        mem.update_fields = update_fields  # type: ignore[method-assign]
        probe = start_probe(go_group=True)
        self.assertIn("kinks", current_question(probe).lower())
        probe = apply_probe_answer(
            probe,
            "I like humiliation, cuckolding and SPH. Hard limits: blood",
            memory=mem,
        )
        self.assertEqual(probe["step"], "toys")
        self.assertTrue(probe["active"])
        self.assertIn("humiliation", str(probe["answers"].get("kinks") or "").lower())
        director = format_probe_director(probe, room="group")
        self.assertIn("toys", director.lower())


class TeasePlayTests(unittest.TestCase):
    def test_detects_porn_and_games(self) -> None:
        self.assertTrue(wants_porn("find a video to tease him"))
        self.assertTrue(wants_porn("suggest porn that matches the lock"))
        self.assertFalse(wants_porn("add an hour"))
        self.assertTrue(wants_game("create a game for us to play"))
        self.assertTrue(wants_online_ideas("look online if you need ideas"))

    def test_genre_follows_kit_and_bull(self) -> None:
        tags = current_genre(
            session_kinks=["SPH"],
            memory_kinks=["wax"],
            play_flavors="denial",
            persona="friend",
            sex="male",
        )
        joined = " ".join(tags).lower()
        self.assertIn("chastity", joined)
        self.assertIn("cuckolding", joined)
        self.assertIn("sph", joined)
        q = genre_query(tags)
        self.assertIn("cuckold", q.lower())
        self.assertIn("pornhub.com/video/search", search_url(tags))

    def test_game_director_names_a_hook(self) -> None:
        games = pick_local_games(
            tags=["Chastity"], toys=["Plug"], persona="friend", sex="male", count=3
        )
        self.assertEqual(games[0]["id"], "bull_night")
        text = format_game_director(
            tags=["Cuckolding", "Chastity"],
            toys=["Plug"],
            persona="bull",
            ideas=["Reddit idea about a locked cuck"],
            room="private",
        )
        self.assertIn("Bull night", text)
        self.assertIn("ONE game", text)

    def test_porn_director_uses_real_or_search(self) -> None:
        tags = ["Cuckolding", "Chastity"]
        with_links = format_porn_director(
            tags=tags,
            videos=[
                {
                    "title": "Locked cuck watches",
                    "url": "https://www.pornhub.com/view_video.php?viewkey=abc",
                    "duration": "10:00",
                }
            ],
            room="group",
        )
        self.assertIn("viewkey=abc", with_links)
        self.assertIn("Locked cuck watches", with_links)
        fallback = format_porn_director(tags=tags, videos=[], room="private")
        self.assertIn("pornhub.com/video/search", fallback)


class HandoffTests(unittest.TestCase):
    def test_take_control_is_a_handoff(self) -> None:
        from app.handoff import (
            apply_handoff,
            format_handoff_director,
            start_handoff,
            wants_handoff,
            wants_handoff_go,
        )
        from app.speaker_guard import should_take_to_private

        self.assertTrue(wants_handoff("take control of him"))
        self.assertTrue(wants_handoff("you're in charge"))
        self.assertTrue(wants_handoff_go("go ahead, tell him"))
        self.assertTrue(should_take_to_private("take control of him"))
        self.assertFalse(should_take_to_private("take control of him and tell him"))

        state = start_handoff()
        self.assertEqual(state["phase"], "pitch")
        pitch = format_handoff_director(state, room="private")
        self.assertIn("TAKE CONTROL", pitch)
        self.assertIn("ONE real question", pitch)
        self.assertIn("questionnaire", pitch.lower())

        shaping = apply_handoff(state, "You can tease him. I keep the keys.")
        self.assertEqual(shaping["phase"], "shaping")
        running = apply_handoff(shaping, "go, tell him")
        self.assertEqual(running["phase"], "running")
        group = format_handoff_director(running, room="group")
        self.assertIn("running him", group.lower())


if __name__ == "__main__":
    unittest.main()
