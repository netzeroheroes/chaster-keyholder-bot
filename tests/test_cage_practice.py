import unittest

from app.cage_practice import orders_caged_touch, rewrite_caged_touch
from app.chat_service import extract_spoken_user
from app.lock_guard import scrub_lock_hallucinations
from app.bridge import GroupBridge
from app.speaker_guard import (
    brief_private_delivery,
    collapse_idea_list,
    looks_like_plan_spoiler,
    mistreats_domme_as_sub,
    planning_stays_private,
    private_should_be_brief,
    soften_group_tease,
    strip_leaked_instructions,
    wants_him_told,
    wants_to_be_free,
)
from app.chaster import BLOCKED_EXTENSION_SLUGS
from app.rad_lockbox import summarize_lockbox


class CagePracticeTests(unittest.TestCase):
    def test_rewrites_touch_yourself_reward(self) -> None:
        src = (
            "You've been a very obedient boy, haven't you? "
            "I think you deserve a little reward—go ahead and touch yourself, "
            "but keep it gentle."
        )
        self.assertTrue(orders_caged_touch(src))
        out = rewrite_caged_touch(src)
        low = out.lower()
        self.assertNotIn("touch yourself", low)
        self.assertNotIn("keep it gentle", low)
        self.assertIn("cage", low)

    def test_leaves_normal_tease(self) -> None:
        src = "Stay locked. Thank her for the cage."
        self.assertFalse(orders_caged_touch(src))
        self.assertEqual(rewrite_caged_touch(src), src)

    def test_strips_hygiene_lock_tag(self) -> None:
        src = (
            "keyholder. I'll get the lockee's hygiene window opened up. "
            "[[[LOCK pillory 3600]]]"
        )
        out = strip_leaked_instructions(src)
        low = out.lower()
        self.assertNotIn("[[[lock", low)
        self.assertNotIn("pillory", low)
        self.assertNotIn("hygiene window", low)

    def test_ideas_about_him_are_not_misaddress(self) -> None:
        ask = "i want to play with his cock what games can i play"
        reply = (
            "You could tease his cock with a feather through the cage, "
            "make him kneel and describe it, or keep him locked while you play."
        )
        self.assertFalse(mistreats_domme_as_sub(reply, user_message=ask))
        self.assertFalse(mistreats_domme_as_sub(reply))

    def test_hygiene_to_her_is_misaddress(self) -> None:
        self.assertTrue(
            mistreats_domme_as_sub("I gave you a hygiene unlock. Use that time wisely.")
        )

    def test_extracts_spoken_from_bloated_user(self) -> None:
        blob = (
            "[Domme (@TheBosses)]: maybe let him out of it maybe you could drop him some hint's\n"
            "[IDENTITY: This message is from the human Domme / Chaster keyholder.]\n"
            "[ADDRESS: Reply TO her]\n"
            "[CHASTER LIVE STATUS]\n- Remaining: hidden"
        )
        self.assertEqual(
            extract_spoken_user(blob),
            "maybe let him out of it maybe you could drop him some hint's",
        )
        focused = (
            'THEY SAID (answer this — do not ignore it):\n"""drop a hint"""\n'
            "Speaker: Domme."
        )
        self.assertEqual(extract_spoken_user(focused), "drop a hint")

    def test_collapses_hint_list(self) -> None:
        src = (
            "Certainly! Here are some hints and teasers you could drop:\n"
            "1. I wonder what it feels like to be so restricted.\n"
            "2. Maybe I'll let you out if you behave.\n"
            "3. Think about what I might do.\n"
        )
        out = collapse_idea_list(src)
        self.assertNotIn("Certainly", out)
        self.assertNotIn("2.", out)
        self.assertIn("restricted", out.lower())

    def test_softens_spoiler_and_homework(self) -> None:
        src = (
            "Lockee, TheBosses might be playing with your cock later - "
            "but you'll be waiting awhile. For now, tell me in explicit detail "
            "about that cage. Then assume a thankful posture."
        )
        out = soften_group_tease(src)
        low = out.lower()
        self.assertNotIn("playing with your cock", low)
        self.assertNotIn("explicit detail", low)
        self.assertNotIn("thankful posture", low)
        self.assertTrue(len(out) >= 16)

    def test_softens_concrete_plan_dump(self) -> None:
        src = "Tonight she'll use the plug, then edge you until you cry."
        out = soften_group_tease(src)
        low = out.lower()
        self.assertNotIn("plug", low)
        self.assertNotIn("edge you", low)
        self.assertTrue(looks_like_plan_spoiler(src))
        self.assertFalse(looks_like_plan_spoiler("Stay denied. That cage stays on."))
        self.assertEqual(
            soften_group_tease("Stay denied. That cage stays on."),
            "Stay denied. That cage stays on.",
        )

    def test_softens_numbered_plan_list(self) -> None:
        src = "1. Plug him tonight\n2. Edge him tomorrow\n3. Deny all week"
        out = soften_group_tease(src)
        self.assertNotIn("Plug", out)
        self.assertNotIn("1.", out)

    def test_planning_stays_private_unless_tell_him(self) -> None:
        self.assertTrue(planning_stays_private("what ideas can I use on him"))
        self.assertTrue(planning_stays_private("give me some hints"))
        self.assertFalse(planning_stays_private("drop him some hints"))
        self.assertTrue(wants_him_told("drop him some hints"))
        self.assertTrue(wants_him_told("tease him"))
        self.assertFalse(wants_him_told("what ideas can I use"))
        bridge = GroupBridge()
        self.assertFalse(bridge.wants_group_post("what ideas can I use on him"))
        self.assertTrue(bridge.wants_group_post("drop him some hints"))
        self.assertTrue(bridge.wants_group_post("tease him now"))
        self.assertTrue(wants_him_told("taunt him and drop subtle hint's"))
        self.assertTrue(wants_him_told("prepare him mentally for it"))
        self.assertTrue(bridge.wants_group_post("prepare him mentally for it"))
        self.assertTrue(private_should_be_brief(
            "Tonight you won't just be teased, I whisper to him"
        ))
        self.assertTrue(private_should_be_brief(
            "You can start by building the anticipation. Tell him that tonight..."
        ))
        self.assertIn("Group", brief_private_delivery())

    def test_wants_to_be_free(self) -> None:
        self.assertTrue(wants_to_be_free("i would to be free"))
        self.assertTrue(wants_to_be_free("please unlock me"))
        self.assertFalse(wants_to_be_free("hello"))

    def test_scrub_keeps_tease_not_fact_dump(self) -> None:
        src = (
            "Stay with that ache. I added 3 days to your lock. "
            "Maybe if you earn it."
        )
        out = scrub_lock_hallucinations(
            src, live_remaining="hidden", had_action_facts=False
        )
        self.assertIsNotNone(out)
        low = (out or "").lower()
        self.assertNotIn("don't invent", low)
        self.assertNotIn("live remaining", low)
        self.assertTrue("earn" in low or "ache" in low)

    def test_hygiene_plugin_blocked(self) -> None:
        self.assertIn("temporary-opening", BLOCKED_EXTENSION_SLUGS)


class LockboxSummaryTests(unittest.TestCase):
    def test_locked_when_active(self) -> None:
        view = summarize_lockbox(
            {
                "configured": True,
                "session": {"lockState": "locked", "isActive": True},
            }
        )
        self.assertTrue(view["locked"])
        self.assertEqual(view["label"], "LOCKED")

    def test_open_when_unlocked(self) -> None:
        view = summarize_lockbox(
            {
                "configured": True,
                "session": {"lockState": "unlocked", "isActive": True},
            }
        )
        self.assertFalse(view["locked"])
        self.assertEqual(view["label"], "OPEN")

    def test_not_configured(self) -> None:
        view = summarize_lockbox({"configured": False})
        self.assertIsNone(view["locked"])
        self.assertEqual(view["label"], "not configured")


if __name__ == "__main__":
    unittest.main()
