from __future__ import annotations

import base64
import logging
import re
import uuid
from pathlib import Path

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
IMAGES_DIR = DATA_DIR / "images"

IMAGE_BLOCK = re.compile(
    r"\[\[\[IMAGE\]\]\](.*?)\[\[\[/IMAGE\]\]\]",
    re.DOTALL | re.IGNORECASE,
)

# Flux / Seedream belong on POST /api/v1/images — never chat modalities.
_CHAT_IMAGE_MODELS = frozenset(
    {
        "google/gemini-2.5-flash-image",
        "google/gemini-3.1-flash-image",
        "google/gemini-3.1-flash-lite-image",
        "google/gemini-3-pro-image",
        "google/gemini-3-pro-image-preview",
        "google/gemini-3.1-flash-image-preview",
        "openai/gpt-5-image",
        "openai/gpt-5-image-mini",
        "openai/gpt-5.4-image-2",
        "openai/gpt-image-1",
        "openai/gpt-image-1-mini",
        "openai/gpt-image-2",
    }
)

_DEFAULT_FALLBACKS = (
    "bytedance-seed/seedream-4.5",
    "black-forest-labs/flux.2-klein-4b",
    "google/gemini-2.5-flash-image",
)

_SOFTEN = (
    (re.compile(r"\bjodphurs\b", re.I), "jodhpurs"),
    (re.compile(r"\bdominatrix\b", re.I), "confident woman"),
    (re.compile(r"\bdomme\b", re.I), "confident woman"),
    (re.compile(r"\b(chastity(\s+(belt|cage|device))?|cock cage)\b", re.I), ""),
    (re.compile(r"\blatex\b", re.I), "shiny black outfit"),
    (re.compile(r"\b(bdsm|bondage|fetish)\b", re.I), ""),
    (re.compile(r"\b(nude|naked|nsfw)\b", re.I), "fashion editorial"),
    (re.compile(r"\bkeyee\b", re.I), ""),
)

_PIC_REQUEST = re.compile(
    r"\b(?:please\s+)?(?:send|generate|make|create|draw|post)\b"
    r".{0,80}?\b(?:pic|picture|image|photo|tease(?:\s+pic(?:ture)?)?)\b"
    r"(?:\s+of\s+(?P<of>.+))?",
    re.I | re.S,
)

_SENT_CLAIM_SENTENCE = re.compile(
    r"[^.!?\n]*\b("
    r"as per your instructions|"
    r"i('ve| have)? sent|"
    r"sent (him|her|the lockee|the sub) a (pic|picture|image|photo)|"
    r"with an attached (note|image|picture|photo)|"
    r"i have sent him a picture"
    r")\b[^.!?\n]*[.!?]?",
    re.I,
)

_GENERIC_TEASE = (
    "Adult 18+ fashion photograph: confident woman, tailored outfit, "
    "studio lighting, no underage"
)


def prompt_from_request(message: str, *, fallback: str = "") -> str:
    """Turn 'send him a picture of X' into an image prompt that keeps her subject."""
    text = (message or "").strip()
    match = _PIC_REQUEST.search(text)
    subject = ""
    if match:
        subject = (match.group("of") or "").strip()
        subject = re.split(
            r"\b(?:and|with a note|saying|that says)\b",
            subject,
            maxsplit=1,
            flags=re.I,
        )[0].strip()
        subject = re.sub(r"[.!?]+$", "", subject).strip()
        subject = re.sub(r"\s+", " ", subject)
    if subject and len(subject) >= 3:
        return soften_image_prompt(
            f"Adult fashion photograph: {subject}. "
            "Studio lighting, realistic clothing, no underage"
        )
    return fallback or _GENERIC_TEASE


def soften_image_prompt(prompt: str) -> str:
    """Rewrite a tease request into fashion-photo language filters are likelier to allow."""
    out = prompt or ""
    for pat, repl in _SOFTEN:
        out = pat.sub(repl, out)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+,", ",", out)
    out = out.strip(" ,")
    if not re.search(r"\b(18\+|adult|mature)\b", out, re.I):
        out = f"{out}, adult 18+ fashion photograph"
    if "fashion" not in out.lower():
        out = f"{out}, fashion editorial"
    return out.strip()


def strip_unsent_image_claims(text: str) -> str:
    """Drop sentences that claim a picture was already sent."""
    cleaned = _SENT_CLAIM_SENTENCE.sub("", text or "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()
    return cleaned


def user_facing_image_error(exc: BaseException) -> str:
    msg = str(exc or "")
    lower = msg.lower()
    if "402" in msg or "credit" in lower:
        return "Image generation needs OpenRouter credits. Nothing was sent."
    if "disabled" in lower:
        return "Image generation is disabled. Nothing was sent."
    return "Couldn't generate that picture. Nothing was sent."


def _ext_from_media(media_type: str, header: str = "") -> str:
    blob = f"{media_type} {header}".lower()
    if "jpeg" in blob or "jpg" in blob:
        return "jpg"
    if "webp" in blob:
        return "webp"
    return "png"


def _decode_data_url(url: str) -> tuple[bytes, str]:
    header, b64 = url.split(",", 1)
    return base64.b64decode(b64), _ext_from_media("", header)


class ImageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return bool(self.settings.image_enabled and self.settings.llm_api_key)

    def extract_prompts(self, text: str) -> tuple[str, list[str]]:
        prompts = [m.strip() for m in IMAGE_BLOCK.findall(text or "") if m.strip()]
        cleaned = IMAGE_BLOCK.sub("", text or "").strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned, prompts

    def _model_queue(self) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        extras = [
            m.strip()
            for m in (self.settings.image_fallback_models or "").split(",")
            if m.strip()
        ]
        for model in (self.settings.image_model, *extras, *_DEFAULT_FALLBACKS):
            if model and model not in seen:
                seen.add(model)
                ordered.append(model)
        return ordered

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.openrouter_site_url,
            "X-Title": self.settings.openrouter_app_name,
        }

    def _save(self, raw: bytes, ext: str, prompt: str, model: str) -> dict:
        image_id = uuid.uuid4().hex
        path = IMAGES_DIR / f"{image_id}.{ext}"
        path.write_bytes(raw)
        return {
            "id": image_id,
            "url": f"/media/images/{image_id}.{ext}",
            "prompt": prompt,
            "model": model,
        }

    def _bytes_from_item(self, item: dict) -> tuple[bytes, str] | None:
        if not isinstance(item, dict):
            return None
        media = str(item.get("media_type") or "image/png")
        b64 = item.get("b64_json") or item.get("b64") or ""
        url = str(item.get("url") or "")
        nested = item.get("image_url")
        if isinstance(nested, dict):
            url = url or str(nested.get("url") or "")
        elif isinstance(nested, str):
            url = url or nested
        if b64:
            if str(b64).startswith("data:"):
                return _decode_data_url(str(b64))
            return base64.b64decode(str(b64)), _ext_from_media(media)
        if url.startswith("data:"):
            return _decode_data_url(url)
        return None

    async def _download(self, client: httpx.AsyncClient, url: str) -> tuple[bytes, str]:
        response = await client.get(url)
        response.raise_for_status()
        ctype = response.headers.get("content-type") or "image/png"
        return response.content, _ext_from_media(ctype)

    async def _parse_images_json(
        self,
        data: dict,
        *,
        client: httpx.AsyncClient,
    ) -> tuple[bytes, str]:
        items = data.get("data") or []
        if not items:
            raise RuntimeError("No image data returned")
        first = items[0] if isinstance(items[0], dict) else {}
        parsed = self._bytes_from_item(first)
        if parsed:
            return parsed
        url = str(first.get("url") or "")
        nested = first.get("image_url")
        if isinstance(nested, dict):
            url = url or str(nested.get("url") or "")
        if url.startswith("http"):
            return await self._download(client, url)
        raise RuntimeError("Image response missing b64_json or url")

    async def generate(
        self,
        prompt: str,
        *,
        aspect_ratio: str | None = None,
    ) -> dict:
        if not self.enabled:
            raise RuntimeError("Image generation is disabled (set IMAGE_ENABLED=true)")

        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("Empty image prompt")

        if not re.search(r"\b(18\+|adult|mature)\b", prompt, re.I):
            prompt = f"{prompt}, adult 18+ fashion photograph"

        ratio = aspect_ratio or self.settings.image_aspect_ratio
        prompts = [prompt]
        soft = soften_image_prompt(prompt)
        if soft.lower() != prompt.lower():
            prompts.append(soft)
        errors: list[str] = []

        async with httpx.AsyncClient(timeout=180.0) as client:
            for model in self._model_queue():
                for attempt in prompts:
                    try:
                        return await self._generate_with_model(
                            attempt, model=model, client=client, aspect_ratio=ratio
                        )
                    except RuntimeError as exc:
                        msg = str(exc)
                        if "credits" in msg.lower() or "402" in msg:
                            raise
                        log.warning("Image model %s failed: %s", model, msg[:300])
                        errors.append(f"{model}: {msg[:160]}")

        detail = errors[0] if errors else "no models tried"
        raise RuntimeError(f"Image generation failed ({detail})")

    async def _generate_with_model(
        self,
        prompt: str,
        *,
        model: str,
        client: httpx.AsyncClient,
        aspect_ratio: str | None,
    ) -> dict:
        last_error = "unknown error"
        for use_ratio in (True, False):
            payload: dict = {"model": model, "prompt": prompt}
            if use_ratio and aspect_ratio:
                payload["aspect_ratio"] = aspect_ratio
            response = await client.post(
                "https://openrouter.ai/api/v1/images",
                headers=self._headers(),
                json=payload,
            )
            if response.status_code == 402:
                raise RuntimeError(
                    "OpenRouter needs credits for image generation. "
                    "Add credits at https://openrouter.ai/settings/credits"
                )
            if response.status_code < 400:
                raw, ext = await self._parse_images_json(response.json(), client=client)
                return self._save(raw, ext, prompt, model)
            last_error = f"{response.status_code}: {response.text[:240]}"
            log.warning("OpenRouter /images %s failed: %s", model, last_error)
            if response.status_code in {401, 403}:
                break
            if not use_ratio:
                break

        if model in _CHAT_IMAGE_MODELS:
            return await self._generate_via_chat(prompt, model=model, client=client)
        raise RuntimeError(last_error)

    async def _generate_via_chat(
        self,
        prompt: str,
        *,
        model: str,
        client: httpx.AsyncClient,
    ) -> dict:
        if model not in _CHAT_IMAGE_MODELS:
            raise RuntimeError(
                f"{model} does not support chat image modalities — use /api/v1/images"
            )
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": f"Generate an image: {prompt}"}],
            "modalities": ["image", "text"],
        }
        response = await client.post(url, headers=self._headers(), json=payload)
        if response.status_code == 402:
            raise RuntimeError(
                "OpenRouter needs credits for image generation. "
                "Add credits at https://openrouter.ai/settings/credits"
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Chat image fallback failed ({response.status_code})"
            )
        result = response.json()
        message = (result.get("choices") or [{}])[0].get("message") or {}
        images = message.get("images") or []
        if not images:
            raise RuntimeError("No images in chat response")

        first = images[0] if images else {}
        parsed = self._bytes_from_item(first if isinstance(first, dict) else {})
        if parsed:
            raw, ext = parsed
            return self._save(raw, ext, prompt, model)

        image_meta = first.get("image_url") if isinstance(first, dict) else None
        image_url = ""
        if isinstance(image_meta, dict):
            image_url = str(image_meta.get("url") or "")
        elif isinstance(image_meta, str):
            image_url = image_meta
        if image_url.startswith("data:"):
            raw, ext = _decode_data_url(image_url)
            return self._save(raw, ext, prompt, model)
        if image_url.startswith("http"):
            raw, ext = await self._download(client, image_url)
            return self._save(raw, ext, prompt, model)
        raise RuntimeError("Chat image response missing image bytes")
