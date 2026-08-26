import unittest

from app.bot_persona import (
    default_sex_for,
    format_persona_block,
    format_scene_persona_override,
    is_bull_voice,
    normalize_persona,
    resolve_persona,
    scene_lead_director,
    wants_her_attention,
    wants_scene_lead,
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
from app.chaster_actions import parse_chaster_intent
from app.tease_play import (
    current_genre,
    format_game_director,
    format_porn_director,
    format_porn_group_line,
    format_porn_private_ack,
    genre_query,
    is_specific_tease_link,
    pick_local_games,
    reddit_media_from_listing,
    redgif_iframe,
    search_url,
    subs_for_tags,
    tease_media_fields,
    wanted_media_kind,
    parse_tease_batch,
    rank_tease_items,
    theme_score,
    wants_game,
    wants_tease_go,
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
        self.assertIn("YOU ARE THE BULL", text)
        self.assertIn("You are a MAN", text)
        self.assertNotIn("wicked woman", text)
        you, frame = identity_lines(bot_name="Rex")
        self.assertIn("MAN", you)
        self.assertIn("cuckold", frame.lower())
        voice = rc.format_voice_block(room="group")
        self.assertIn("Male voice", voice)
        self.assertIn("She's with me tonight", voice)
        self.assertNotIn("talked her into locking that pathetic thing", voice)
        private_voice = rc.format_voice_block(room="private")
        self.assertIn("You are her bull", private_voice)
        self.assertIn("Come here. He's locked", private_voice)
        self.assertTrue(is_bull_voice())
        override = format_scene_persona_override(room="private")
        self.assertIn("HARD OVERRIDE", override)
        self.assertIn("secretary spinning ideas", override)

    def test_male_sex_alone_promotes_friend_to_bull(self) -> None:
        from app import runtime_controls as rc

        ctrl = rc.RuntimeControls()
        ctrl.save = lambda: None  # type: ignore[method-assign]
        self.assertEqual(ctrl.bot_persona, "friend")
        ctrl.update(bot_sex="male")
        self.assertEqual(ctrl.bot_sex, "male")
        self.assertEqual(ctrl.bot_persona, "bull")
        ctrl.update(bot_persona="friend", bot_sex="male")
        self.assertEqual(ctrl.bot_persona, "friend")
        self.assertTrue(wants_her_attention("what about the 2 of us?"))
        self.assertTrue(wants_her_attention("i think i need some attention"))
        self.assertTrue(wants_her_attention("I want you tonight"))
        self.assertFalse(wants_her_attention("i think he needs to know his place"))
        self.assertFalse(wants_her_attention("i want you to tease him"))

    def test_naughty_cue_starts_a_scene_not_a_timer(self) -> None:
        from app.lock_guard import strip_unsolicited_lock_dump

        cue = "im feeling naughty what should we do today"
        self.assertTrue(wants_scene_lead(cue))
        self.assertFalse(wants_scene_lead("hows his lock"))
        director = scene_lead_director(room="private", bull_voice=True)
        self.assertIn("START a specific situation", director)
        self.assertIn("any ideas", director.lower())
        dumped = strip_unsolicited_lock_dump(
            "3 days, 12 hours, 14 minutes. Now any ideas?"
        )
        self.assertNotIn("3 days", dumped)
        self.assertNotIn("any ideas", dumped.lower())

    def test_bull_flirt_is_not_her_as_lockee(self) -> None:
        from app.speaker_guard import (
            mistreats_domme_as_sub,
            repair_domme_misaddress,
        )

        ask = "i think i need some attention"
        reply = (
            "Come here. He's locked — that's the point. "
            "Tell me what you want from me while he waits."
        )
        self.assertFalse(
            mistreats_domme_as_sub(reply, user_message=ask, bull_voice=True)
        )
        self.assertFalse(
            mistreats_domme_as_sub(
                "Patience, pet. He's not getting you tonight.",
                user_message=ask,
                bull_voice=True,
            )
        )
        self.assertTrue(
            mistreats_domme_as_sub(
                "I gave you a hygiene unlock. Use that time wisely.",
                bull_voice=True,
            )
        )
        repaired = repair_domme_misaddress(
            domme_title="TheBosses",
            sub_name="him",
            original_topic=ask,
            bull_voice=True,
        )
        self.assertNotIn("spin ideas", repaired.lower())
        self.assertNotIn("you play, i help", repaired.lower())
        self.assertIn("what do you want from me", repaired.lower())

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
        self.assertTrue(wants_porn("send him some videos"))
        self.assertTrue(wants_porn("send him a picture or video"))
        self.assertTrue(wants_porn("send him a picture"))
        self.assertTrue(wants_porn("send him a pic"))
        self.assertTrue(wants_porn("5 clips 1 minute apart"))
        self.assertTrue(wants_porn("1 every minute for 5 minutes"))
        self.assertEqual(wanted_media_kind("send him a picture"), "image")
        self.assertEqual(wanted_media_kind("5 clips 1 minute apart"), "video")
        self.assertEqual(wanted_media_kind("send him a picture or video"), "any")
        self.assertEqual(parse_tease_batch("5 clips 1 minute apart"), (5, 60))
        self.assertEqual(parse_tease_batch("1 every minute for 5 minutes")[1], 60)
        self.assertGreaterEqual(parse_tease_batch("1 every minute for 5 minutes")[0], 5)
        self.assertTrue(wants_tease_go("i asked you to do it"))
        self.assertTrue(
            wants_porn("i think he should watch porn to enforce his situation")
        )
        self.assertTrue(
            wants_porn(
                "Find a porn video that matches this lock's current kinks "
                "and tease him with it."
            )
        )
        self.assertFalse(wants_porn("add an hour"))
        self.assertTrue(wants_game("create a game for us to play"))
        self.assertTrue(wants_online_ideas("look online if you need ideas"))
        self.assertTrue(wants_tease_go("do it"))
        self.assertTrue(wants_tease_go("send it"))
        self.assertFalse(wants_tease_go("do the visibility"))
        self.assertIsNone(parse_chaster_intent("do it"))
        self.assertIsNone(parse_chaster_intent("send it"))
        line = format_porn_group_line(
            title="Locked cuck watches",
            url="https://www.pornhub.com/view_video.php?viewkey=abc",
            bull_voice=True,
        )
        self.assertIn("viewkey=abc", line)
        self.assertNotIn("remaining", line.lower())
        ack = format_porn_private_ack(line)
        self.assertIn("Sent.", ack)
        self.assertIn("Sent to group", ack)
        self.assertIn("viewkey=abc", ack)
        self.assertNotIn("I couldn't save a keyholder note", ack)

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
        self.assertIn("reddit.com/r/MaleChastity", search_url(tags))
        self.assertIn("MaleChastity", subs_for_tags(tags))
        self.assertIn("Cuckold", subs_for_tags(["Cuckolding", "Chastity"]))

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
        self.assertIn("Reddit", fallback)
        self.assertNotIn("pornhub.com/video/search", fallback)
        self.assertNotIn("Give this search", fallback)

    def test_reddit_media_is_a_real_click(self) -> None:
        listing = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Locked and watching",
                            "url": "https://i.redd.it/abc123.jpg",
                            "permalink": "/r/MaleChastity/comments/xyz/locked/",
                            "over_18": True,
                            "stickied": False,
                            "is_self": False,
                            "domain": "i.redd.it",
                            "post_hint": "image",
                        }
                    },
                    {
                        "data": {
                            "title": "teen tease",
                            "url": "https://i.redd.it/nope.jpg",
                            "permalink": "/r/x/comments/1/x/",
                            "over_18": True,
                            "is_self": False,
                            "domain": "i.redd.it",
                            "post_hint": "image",
                        }
                    },
                    {
                        "data": {
                            "title": "Redgif for the cuck",
                            "url": "https://www.redgifs.com/watch/exampleclip",
                            "permalink": "/r/Cuckold/comments/abc/redgif/",
                            "over_18": True,
                            "is_self": False,
                            "domain": "redgifs.com",
                            "post_hint": "rich:video",
                        }
                    },
                    {
                        "data": {
                            "title": "Just a text post",
                            "url": "https://www.reddit.com/r/MaleChastity/comments/s/self/",
                            "permalink": "/r/MaleChastity/comments/s/self/",
                            "over_18": True,
                            "is_self": True,
                            "domain": "self.MaleChastity",
                        }
                    },
                ]
            }
        }
        items = reddit_media_from_listing(listing)
        urls = [item["url"] for item in items]
        self.assertIn("https://i.redd.it/abc123.jpg", urls)
        pic_item = next(i for i in items if "abc123.jpg" in i["url"])
        self.assertEqual(pic_item.get("image_url"), "https://i.redd.it/abc123.jpg")
        self.assertEqual(
            redgif_iframe("https://www.redgifs.com/watch/exampleclip"),
            "https://www.redgifs.com/ifr/exampleclip",
        )
        self.assertEqual(
            tease_media_fields(url="https://www.redgifs.com/watch/exampleclip").get(
                "page_url"
            ),
            "https://www.redgifs.com/watch/exampleclip",
        )
        self.assertEqual(
            tease_media_fields(url="https://www.redgifs.com/watch/exampleclip").get(
                "embed_url"
            ),
            "https://www.redgifs.com/ifr/exampleclip",
        )
        self.assertIn("https://www.redgifs.com/watch/exampleclip", urls)
        self.assertFalse(any("nope.jpg" in u for u in urls))
        self.assertFalse(any("/self/" in u for u in urls))
        pic = format_porn_group_line(
            title="Locked and watching",
            url="https://i.redd.it/abc123.jpg",
            kind="image",
        )
        self.assertIn("Look at", pic)
        self.assertIn("i.redd.it/abc123.jpg", pic)
        self.assertTrue(is_specific_tease_link("https://i.redd.it/abc123.jpg"))
        self.assertTrue(
            is_specific_tease_link(
                "https://www.reddit.com/r/MaleChastity/comments/xyz/locked/"
            )
        )
        self.assertFalse(
            is_specific_tease_link(
                "https://www.pornhub.com/video/search?search=chastity+cage+cuckold"
            )
        )
        self.assertFalse(is_specific_tease_link("https://www.reddit.com/r/MaleChastity/"))
        tagged = [
            {
                "title": "Amateur OnlyFans",
                "kind": "video",
                "url": "https://www.redgifs.com/watch/aaa",
                "theme_blob": "onlyfans tits amateur",
            },
            {
                "title": "Locked cuck",
                "kind": "video",
                "url": "https://www.redgifs.com/watch/bbb",
                "theme_blob": "chastity cuckold cage",
            },
            {
                "title": "Cage pic",
                "kind": "image",
                "url": "https://i.redd.it/cage.jpg",
                "theme_blob": "chastity cage",
            },
        ]
        ranked = rank_tease_items(
            tagged, ["Chastity", "Cuckolding"], kind="video"
        )
        self.assertEqual(ranked[0]["title"], "Locked cuck")
        self.assertFalse(any(item["kind"] == "image" for item in ranked))
        pics = rank_tease_items(tagged, ["Chastity"], kind="image")
        self.assertEqual(pics[0]["kind"], "image")
        self.assertGreater(
            theme_score(tagged[1], ["Chastity", "Cuckolding"]),
            theme_score(tagged[0], ["Chastity", "Cuckolding"]),
        )
        pullpush = {
            "data": [
                {
                    "title": "Cage pic",
                    "url": "https://i.redd.it/fresh.jpg",
                    "permalink": "/r/MaleChastity/comments/zz/cage/",
                    "over_18": True,
                    "is_self": False,
                    "domain": "i.redd.it",
                    "post_hint": "image",
                }
            ]
        }
        pulled = reddit_media_from_listing(pullpush)
        self.assertEqual(pulled[0]["url"], "https://i.redd.it/fresh.jpg")
        self.assertTrue(
            is_specific_tease_link(
                "https://v3.redgifs.com/watch/712286666547560214"
            )
        )


class HandoffTests(unittest.TestCase):
    def test_take_control_is_a_handoff(self) -> None:
        from app.handoff import (
            apply_handoff,
            format_handoff_director,
            format_lead_now_group_line,
            start_handoff,
            wants_handoff,
            wants_handoff_go,
            wants_lead_now,
        )
        from app.lock_guard import looks_like_concierge_ask, strip_unsolicited_lock_dump
        from app.speaker_guard import should_take_to_private

        self.assertTrue(wants_handoff("take control of him"))
        self.assertTrue(wants_handoff("you're in charge"))
        self.assertTrue(wants_handoff_go("go ahead, tell him"))
        self.assertTrue(wants_lead_now("you are running things today"))
        self.assertTrue(wants_lead_now("you are runnng things today"))
        self.assertTrue(
            wants_lead_now(
                "he dosnt get a say in who is the lead he's both of our toys now"
            )
        )
        self.assertFalse(should_take_to_private("take control of him"))
        self.assertFalse(should_take_to_private("you are running things today"))
        self.assertFalse(should_take_to_private("take control of him and tell him"))

        state = start_handoff()
        self.assertEqual(state["phase"], "running")
        private = format_handoff_director(state, room="private")
        self.assertIn("Do NOT ask where to begin", private)
        self.assertNotIn("questionnaire", private.lower())

        running = apply_handoff(state, "go, tell him")
        self.assertEqual(running["phase"], "running")
        group = format_handoff_director(running, room="group")
        self.assertIn("START NOW", group)
        self.assertIn("Do NOT ask her where to begin", group)

        concierge = (
            "So, where do you want to begin, knowing he's locked and I'm right here?"
        )
        self.assertTrue(looks_like_concierge_ask(concierge))
        dumped = strip_unsolicited_lock_dump(concierge)
        self.assertNotIn("where do you want to begin", dumped.lower())
        line = format_lead_now_group_line(
            bull_voice=True, title="Keyholder", sub_name="Lockee"
        )
        self.assertIn("I've got him", line)
        self.assertNotIn("where do you want", line.lower())


if __name__ == "__main__":
    unittest.main()
