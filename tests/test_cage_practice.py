import unittest

from app.cage_practice import orders_caged_touch, rewrite_caged_touch
from app.speaker_guard import mistreats_domme_as_sub, strip_leaked_instructions
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
