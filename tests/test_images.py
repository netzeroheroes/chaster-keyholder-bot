import unittest

from app.images import (
    prompt_from_request,
    soften_image_prompt,
    strip_unsent_image_claims,
    user_facing_image_error,
)
from app.speaker_guard import (
    fix_mixed_terms,
    has_chat_chrome,
    invents_night_out,
    looks_like_image_dump,
    strip_chat_chrome,
    strip_invented_night_out,
    strip_leaked_instructions,
    strip_stage_directions,
)


class PromptFromRequestTests(unittest.TestCase):
    def test_keeps_jodhpurs_subject(self) -> None:
        prompt = prompt_from_request("send him a picture of a domme in jodphurs")
        self.assertIn("jodhpurs", prompt.lower())
        self.assertNotIn("domme", prompt.lower())
        self.assertIn("adult", prompt.lower())

    def test_generic_when_no_subject(self) -> None:
        prompt = prompt_from_request("send him a picture")
        self.assertIn("fashion", prompt.lower())

    def test_softens_censor_bait(self) -> None:
        out = soften_image_prompt("dominatrix in latex with a chastity belt")
        self.assertNotIn("dominatrix", out.lower())
        self.assertNotIn("latex", out.lower())
        self.assertNotIn("chastity", out.lower())
        self.assertIn("jodhpurs", soften_image_prompt("woman in jodphurs").lower())


class UnsentClaimTests(unittest.TestCase):
    def test_strips_false_send(self) -> None:
        text = (
            "As per your instructions, I have sent him a picture of a dominatrix "
            "in jodphurs with an attached note saying he needs to earn his Sub status back. "
            "It's clear that wearing chastity doesn't make him any less horny."
        )
        cleaned = strip_unsent_image_claims(text)
        self.assertNotIn("I have sent", cleaned)
        self.assertNotIn("As per your instructions", cleaned)

    def test_user_facing_hides_raw_404(self) -> None:
        err = user_facing_image_error(
            RuntimeError(
                'Image generation failed (404): {"error":{"message":'
                '"No endpoints found that support the requested output modalities: image, text"}}'
            )
        )
        self.assertNotIn("404", err)
        self.assertNotIn("modalities", err)
        self.assertIn("Nothing was sent", err)


class LockChromeTests(unittest.TestCase):
    def test_strips_lock_username(self) -> None:
        raw = "[LOCK] Chastityguy80:\nAs per your instructions, I have sent him a picture."
        self.assertTrue(has_chat_chrome(raw))
        cleaned = strip_chat_chrome(raw, sub_name="Chastityguy80")
        self.assertNotIn("[LOCK]", cleaned)
        self.assertNotIn("Chastityguy80", cleaned)

    def test_strips_domme_speaker_prefix(self) -> None:
        raw = "TheBosses: Hey there, keyee. I've got a surprise."
        cleaned = strip_chat_chrome(raw, domme_name="TheBosses")
        cleaned = fix_mixed_terms(cleaned, domme_name="TheBosses")
        self.assertFalse(cleaned.lower().startswith("thebosses"))
        self.assertNotIn("keyee", cleaned.lower())


class TermAndDumpTests(unittest.TestCase):
    def test_replaces_human_domme_and_keyee(self) -> None:
        raw = "BOY, have you been thinking about your task for HUMAN DOMME, keyee?"
        cleaned = fix_mixed_terms(raw, domme_name="Sam")
        self.assertNotIn("HUMAN DOMME", cleaned)
        self.assertIn("Sam", cleaned)
        self.assertNotIn("keyee", cleaned.lower())

    def test_strips_invented_keyholder_out(self) -> None:
        raw = "Hey there. I've got a surprise while your keyholder is out."
        self.assertTrue(invents_night_out(raw))
        cleaned = strip_invented_night_out(raw)
        self.assertNotIn("keyholder is out", cleaned.lower())

    def test_strips_leaked_address(self) -> None:
        raw = (
            "it seems like your little lockee has been quite the good boy today. "
            "[ADDRESS: THE KEYHOLDER; YOU WRITE AS YOURSELF] "
            "You help the keyholder run this lock (18+ only). Talk like a real person."
        )
        cleaned = strip_leaked_instructions(raw)
        self.assertNotIn("[ADDRESS", cleaned)
        self.assertNotIn("Talk like a real person", cleaned)
        self.assertIn("good boy", cleaned)

    def test_strips_new_voice_prompt_leak(self) -> None:
        raw = (
            "Stay locked. You are a Dominant woman in this chat (18+ only) — "
            "her co-keyholder, not a bot reading a script. Feel that ache."
        )
        cleaned = strip_leaked_instructions(raw)
        self.assertNotIn("bot reading a script", cleaned)
        self.assertIn("Stay locked", cleaned)

    def test_strips_smirks(self) -> None:
        cleaned = strip_stage_directions("*smirks* Well, hello there.")
        self.assertNotIn("*", cleaned)
        self.assertIn("Well, hello there.", cleaned)

    def test_detects_image_dump(self) -> None:
        raw = (
            "Imagine this: me, dressed in a skintight latex outfit and high heels, "
            "leaning seductively against the wall, biting my bottom lip. "
            "My eyes are locked on you. The air around you crackles."
        )
        self.assertTrue(looks_like_image_dump(raw))


if __name__ == "__main__":
    unittest.main()
