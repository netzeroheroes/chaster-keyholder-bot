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

        # Soft safety: adults-only framing for this bot's use case
        if not re.search(r"\b(18\+|adult|mature)\b", prompt, re.I):
            prompt = f"{prompt}, adult consensual 18+ scene"

        model = self.settings.image_model
        url = "https://openrouter.ai/api/v1/images"
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.openrouter_site_url,
            "X-Title": self.settings.openrouter_app_name,
        }
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio or self.settings.image_aspect_ratio,
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 402:
                raise RuntimeError(
                    "OpenRouter needs credits for image generation. "
                    "Add credits at https://openrouter.ai/settings/credits"
                )
            if response.status_code >= 400:
                log.warning(
                    "OpenRouter /images failed (%s): %s — trying chat modalities",
                    response.status_code,
                    response.text[:300],
                )
                return await self._generate_via_chat(prompt, client=client)

            data = response.json()

        items = data.get("data") or []
        if not items:
            raise RuntimeError(f"No image data returned: {data}")

        b64 = items[0].get("b64_json")
        media_type = items[0].get("media_type") or "image/png"
        if not b64:
            raise RuntimeError("Image response missing b64_json")

        ext = "png"
        if "jpeg" in media_type or "jpg" in media_type:
            ext = "jpg"
        elif "webp" in media_type:
            ext = "webp"

        image_id = uuid.uuid4().hex
        path = IMAGES_DIR / f"{image_id}.{ext}"
        path.write_bytes(base64.b64decode(b64))
        return {
            "id": image_id,
            "url": f"/media/images/{image_id}.{ext}",
            "prompt": prompt,
            "model": model,
        }

    async def _generate_via_chat(self, prompt: str, *, client: httpx.AsyncClient) -> dict:
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.openrouter_site_url,
            "X-Title": self.settings.openrouter_app_name,
        }
        payload = {
            "model": self.settings.image_model,
            "messages": [{"role": "user", "content": f"Generate an image: {prompt}"}],
            "modalities": ["image"],
        }
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code == 402:
            raise RuntimeError(
                "OpenRouter needs credits for image generation. "
                "Add credits at https://openrouter.ai/settings/credits"
            )
        if response.status_code >= 400:
            # Some models want image+text modalities
            payload["modalities"] = ["image", "text"]
            response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Image generation failed ({response.status_code}): {response.text[:500]}"
            )
        result = response.json()
        message = (result.get("choices") or [{}])[0].get("message") or {}
        images = message.get("images") or []
        if not images:
            raise RuntimeError(f"No images in chat response: {result}")

        image_url = images[0].get("image_url", {}).get("url") or ""
        if image_url.startswith("data:"):
            header, b64 = image_url.split(",", 1)
            ext = "png"
            if "jpeg" in header or "jpg" in header:
                ext = "jpg"
            elif "webp" in header:
                ext = "webp"
            raw = base64.b64decode(b64)
        else:
            # remote URL
            img_resp = await client.get(image_url)
            img_resp.raise_for_status()
            raw = img_resp.content
            ext = "png"

        image_id = uuid.uuid4().hex
        path = IMAGES_DIR / f"{image_id}.{ext}"
        path.write_bytes(raw)
        return {
            "id": image_id,
            "url": f"/media/images/{image_id}.{ext}",
            "prompt": prompt,
            "model": self.settings.image_model,
        }
