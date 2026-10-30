"""Provider for Claude models through the Anthropic API (the user's own API key)."""

from __future__ import annotations

import logging
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel

from .base import LLMProvider
from .json_utils import LLMResponseError

logger = logging.getLogger("crowdpod.llm")

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-opus-5-5"
# If the requested model declines for policy reasons, the API retries on its default fallback model
# inside the same call. Models without fallback support simply run alone.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _text(message: Any) -> str:
    return "".join(block.text for block in message.content if block.type == "text").strip()


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, *, api_key: str, model: str = DEFAULT_MODEL, base_url: str = "", effort: str = "low"):
        if not api_key:
            raise ValueError("Claude needs an Anthropic API key")
        # base_url is only for proxies or tests; empty means the official endpoint
        self.client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url or None, timeout=180, max_retries=2)
        self.model = model or DEFAULT_MODEL
        # Personas make many small, quick decisions; low effort keeps runs fast and cheap.
        self.effort = effort

    def _check(self, message: Any, task: str) -> None:
        if message.stop_reason == "refusal":
            detail = getattr(message, "stop_details", None)
            category = getattr(detail, "category", None) if detail else None
            raise LLMResponseError(f"Claude declined the {task} request" + (f" ({category})" if category else ""))
        if message.stop_reason == "max_tokens":
            raise LLMResponseError(f"Claude's {task} reply hit the token limit", finish_reason="length")

    async def complete_json(self, system: str, user: str, schema: type[T], *, task: str, context: dict[str, Any]) -> T:
        message = await self.client.beta.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            output_config={"effort": self.effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        self._check(message, task)
        if message.parsed_output is None:
            raise LLMResponseError(f"Claude returned no structured output for {task}")
        return message.parsed_output

    async def complete_text(self, system: str, user: str, *, task: str, context: dict[str, Any]) -> str:
        message = await self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        self._check(message, task)
        return _text(message)

    async def list_models(self) -> list[str]:
        return sorted([m.id async for m in self.client.models.list()])

    async def aclose(self) -> None:
        await self.client.close()
