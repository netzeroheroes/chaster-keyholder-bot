import unittest

from app import runtime_controls as rc
from app.chaster_actions import ChasterIntent, preflight_block_reason


class BotLockPermissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ctrl = rc.RuntimeControls()
        rc._CONTROLS = self.ctrl
        self.addCleanup(lambda: setattr(rc, "_CONTROLS", None))

    def test_defaults_allow(self) -> None:
        self.assertTrue(rc.bot_lock_action_allowed("freeze"))
        self.assertTrue(rc.bot_lock_action_allowed("unfreeze"))
        self.assertTrue(rc.bot_lock_action_allowed("hide_time"))
        self.assertTrue(rc.bot_lock_action_allowed("add_time", seconds=600))
        self.assertTrue(rc.bot_lock_action_allowed("add_time", seconds=-300))
        self.assertTrue(rc.bot_lock_action_allowed("pillory"))

    def test_disable_freeze_blocks_all_freeze_kinds(self) -> None:
        self.ctrl.bot_allow_freeze = False
        self.assertFalse(rc.bot_lock_action_allowed("freeze"))
        self.assertFalse(rc.bot_lock_action_allowed("unfreeze"))
        self.assertFalse(rc.bot_lock_action_allowed("toggle_freeze"))
        self.assertTrue(rc.bot_lock_action_allowed("hide_time"))

    def test_remove_uses_remove_flag(self) -> None:
        self.ctrl.bot_allow_remove_time = False
        self.assertFalse(rc.bot_lock_action_allowed("add_time", seconds=-600))
        self.assertTrue(rc.bot_lock_action_allowed("add_time", seconds=600))

    def test_preflight_respects_enable_toggles(self) -> None:
        before = {
            "status": "locked",
            "is_frozen": False,
            "display_remaining_time": True,
        }
        self.assertIsNone(preflight_block_reason(ChasterIntent(kind="freeze"), before))
        self.ctrl.bot_allow_freeze = False
        reason = preflight_block_reason(ChasterIntent(kind="freeze"), before)
        self.assertIsNotNone(reason)
        self.assertIn("Settings", reason or "")

    def test_director_lists_disabled(self) -> None:
        self.ctrl.bot_allow_hide_timer = False
        text = rc.format_bot_lock_permissions()
        self.assertIn("Enabled:", text)
        self.assertIn("Disabled: hide/show timer", text)

    def test_voice_block_uses_preset_and_sample(self) -> None:
        self.ctrl.bot_voice = "warm"
        self.ctrl.bot_voice_sample = "Mmm. Stay denied, darling."
        text = rc.format_voice_block()
        self.assertIn("Tone: warm", text)
        self.assertIn("Stay denied, darling", text)
        self.assertIn("Intensity: firm", text)

    def test_voice_includes_quirks_and_intensity(self) -> None:
        self.ctrl.bot_voice = "elegant"
        self.ctrl.bot_intensity = "strict"
        self.ctrl.bot_quirks = "calls him pet"
        text = rc.format_voice_block()
        self.assertIn("Tone: elegant", text)
        self.assertIn("Intensity: strict", text)
        self.assertIn("calls him pet", text)

    def test_group_voice_uses_miss_g_sample(self) -> None:
        self.ctrl.bot_voice_sample = ""
        text = rc.format_voice_block(room="group")
        self.assertIn("GROUP RP", text)
        self.assertIn("That timer isn't yours", text)
        self.assertNotIn("GROUP RP", rc.format_voice_block(room="private"))


if __name__ == "__main__":
    unittest.main()
