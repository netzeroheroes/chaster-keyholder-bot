from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionToolMessageParam,
)

from app.config import Settings
from app.tools.base import ToolRegistry


class ChatAgent:
    """OpenAI-compatible chat loop with optional tool calling."""

    def __init__(
        self,
        settings: Settings,
        tools: ToolRegistry,
        *,
        max_tool_rounds: int = 8,
    ) -> None:
        self.settings = settings
        self.tools = tools
        self.max_tool_rounds = max_tool_rounds

        default_headers: dict[str, str] = {}
        if "openrouter.ai" in settings.llm_base_url:
            # Recommended by OpenRouter for ranking / attribution
            if settings.openrouter_site_url:
                default_headers["HTTP-Referer"] = settings.openrouter_site_url
            if settings.openrouter_app_name:
                default_headers["X-Title"] = settings.openrouter_app_name

        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            default_headers=default_headers or None,
        )

    def _seed_messages(
        self,
        history: list[ChatCompletionMessageParam],
        user_message: str,
        system_prompt: str | None = None,
    ) -> list[ChatCompletionMessageParam]:
        messages: list[ChatCompletionMessageParam] = []
        prompt = (
            system_prompt
            if system_prompt is not None
            else self.settings.system_prompt
        )
        if prompt.strip():
            messages.append({"role": "system", "content": prompt.strip()})
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    async def reply(
        self,
        user_message: str,
        history: list[ChatCompletionMessageParam] | None = None,
        system_prompt: str | None = None,
    ) -> tuple[str, list[ChatCompletionMessageParam]]:
        messages = self._seed_messages(
            history or [],
            user_message,
            system_prompt=system_prompt,
        )
        tool_schemas = (
            self.tools.schemas() if self.settings.llm_enable_tools else []
        )

        for _ in range(self.max_tool_rounds):
            kwargs: dict[str, Any] = {
                "model": self.settings.llm_model,
                "messages": messages,
                # Cap so OpenRouter credit checks don't reserve a huge completion
                "max_tokens": max(256, int(self.settings.llm_max_tokens or 2048)),
                # Reduce copy-paste loops on smaller/uncensored models
                "temperature": 0.9,
                "frequency_penalty": 0.7,
                "presence_penalty": 0.5,
            }
            if tool_schemas:
                kwargs["tools"] = tool_schemas
                kwargs["tool_choice"] = "auto"

            completion = await self.client.chat.completions.create(**kwargs)
            choice = completion.choices[0].message
            tool_calls = choice.tool_calls or []

            assistant_msg: ChatCompletionMessageParam = {
                "role": "assistant",
                "content": choice.content or "",
            }
            if tool_calls:
                assistant_msg["tool_calls"] = [  # type: ignore[typeddict-item]
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)

            if not tool_calls:
                text = (choice.content or "").strip() or "(empty response)"
                return text, messages

            for tc in tool_calls:
                result = await self.tools.call(
                    tc.function.name,
                    tc.function.arguments,
                )
                tool_msg: ChatCompletionToolMessageParam = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
                messages.append(tool_msg)

        return (
            "Stopped after too many tool rounds. Try a simpler request.",
            messages,
        )
