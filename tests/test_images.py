import unittest

from app.images import (
    prompt_from_request,
    strip_unsent_image_claims,
    user_facing_image_error,
)
from app.speaker_guard import has_chat_chrome, strip_chat_chrome


class PromptFromRequestTests(unittest.TestCase):
    def test_keeps_jodhpurs_subject(self) -> None:
        prompt = prompt_from_request("send him a picture of a domme in jodphurs")
        self.assertIn("domme in jodphurs", prompt.lower())
        self.assertIn("18+", prompt)

    def test_generic_when_no_subject(self) -> None:
        prompt = prompt_from_request("send him a picture")
        self.assertIn("tease photo", prompt.lower())


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


if __name__ == "__main__":
    unittest.main()
