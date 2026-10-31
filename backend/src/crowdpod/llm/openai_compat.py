# Adapted from the upstream project listed in NOTICE (AGPL-3.0); modified 2026-10-30.
"""Provider for any OpenAI-compatible Chat Completions endpoint."""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, InternalServerError, RateLimitError
from pydantic import BaseModel, ValidationError

from ..retry import retry_with_backoff_async
from .base import LLMProvider
from .json_utils import LLMResponseError, clean_chat_text, parse_json_object

logger = logging.getLogger("crowdpod.llm")

T = TypeVar("T", bound=BaseModel)

_TRANSIENT = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


def is_gpt5_family(model: str | None) -> bool:
    return bool(model) and model.strip().lower().startswith("gpt-5")


def build_completion_kwargs(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float | None,
    max_tokens: int | None,
    response_format: dict[str, Any] | None,
) -> dict[str, Any]:
    """Request parameters adapted to the model family.

    GPT-5 models reject `temperature` and take `max_completion_tokens`; every other
    model keeps the classic request shape.
    """
    kwargs: dict[str, Any] = {"model": model, "messages": messages}
    if response_format is not None:
        kwargs["response_format"] = response_format
    gpt5 = is_gpt5_family(model)
    if temperature is not None and not gpt5:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_completion_tokens" if gpt5 else "max_tokens"] = max_tokens
    return kwargs


def extract_chat_completion_text(response: Any) -> str:
    """Extract plain text from a chat completion across SDK content shapes."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if message is None:
        return ""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text_obj = item.get("text")
                if isinstance(text_obj, dict):
                    text_obj = text_obj.get("value")
                if isinstance(text_obj, str):
                    chunks.append(text_obj)
                elif isinstance(item.get("content"), str):
                    chunks.append(item["content"])
                continue
            text_obj = getattr(item, "text", None)
            if isinstance(text_obj, dict):
                text_obj = text_obj.get("value")
            if isinstance(text_obj, str):
                chunks.append(text_obj)
                continue
            content_obj = getattr(item, "content", None)
            if isinstance(content_obj, str):
                chunks.append(content_obj)
        return "".join(chunks).strip()
    return str(content or "")


def is_response_format_unsupported(error: Exception) -> bool:
    """Detect an explicit provider rejection of JSON response_format."""
    if getattr(error, "status_code", None) not in {400, 422}:
        return False
    body = getattr(error, "body", None)
    if not isinstance(body, dict):
        return False
    details = body.get("error", body)
    if not isinstance(details, dict):
        return False
    param = str(details.get("param") or "").strip().lower()
    if param == "response_format" or param.startswith("response_format."):
        return True
    message = str(details.get("message") or "").lower()
    if "response_format" not in message:
        return False
    code = str(details.get("code") or "").lower()
    unsupported_codes = {"unsupported_parameter", "unsupported_value", "unknown_parameter", "invalid_parameter"}
    unsupported_phrases = ("not support", "unsupported", "unknown parameter", "unrecognized parameter")
    return code in unsupported_codes or any(p in message for p in unsupported_phrases)


def parse_completion_json(response: Any) -> dict[str, Any]:
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise LLMResponseError("LLM returned no choices")
    finish_reason = getattr(choices[0], "finish_reason", None)
    if finish_reason == "length":
        raise LLMResponseError("LLM JSON output was truncated at the token limit", finish_reason=finish_reason)
    if finish_reason not in {None, "stop"}:
        raise LLMResponseError(f"LLM JSON generation stopped unexpectedly ({finish_reason})", finish_reason=finish_reason)
    return parse_json_object(extract_chat_completion_text(response), finish_reason=finish_reason)


class OpenAICompatProvider(LLMProvider):
    name = "openai"

    def __init__(self, *, base_url: str, api_key: str, model: str, max_tokens: int = 4096):
        if not (base_url and model):
            raise ValueError("CROWDPOD_LLM_BASE_URL and CROWDPOD_LLM_MODEL must be set for the openai provider")
        # Local servers ignore the key, but the SDK requires a non-empty one.
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key or "not-needed", timeout=120)
        self.model = model
        self.max_tokens = max_tokens
        self._json_mode = True  # switched off once if the endpoint rejects response_format

    @retry_with_backoff_async(max_retries=2, initial_delay=2.0, exceptions=_TRANSIENT)
    async def _create(self, **kwargs: Any) -> Any:
        return await self.client.chat.completions.create(**kwargs)

    async def _chat(self, messages: list[dict[str, Any]], *, temperature: float, max_tokens: int | None, json_mode: bool) -> Any:
        while True:
            fmt = {"type": "json_object"} if (json_mode and self._json_mode) else None
            try:
                return await self._create(
                    **build_completion_kwargs(
                        model=self.model, messages=messages, temperature=temperature,
                        max_tokens=max_tokens, response_format=fmt,
                    )
                )
            except Exception as error:
                if fmt is not None and is_response_format_unsupported(error):
                    logger.warning("endpoint rejected response_format; using prompt-only JSON from now on")
                    self._json_mode = False
                    continue
                raise

    async def complete_json(self, system: str, user: str, schema: type[T], *, task: str, context: dict[str, Any]) -> T:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        max_tokens: int | None = self.max_tokens
        last_error: Exception | None = None
        for attempt in range(2):
            response = await self._chat(messages, temperature=0.8 if task == "crowd" else 0.4, max_tokens=max_tokens, json_mode=True)
            try:
                return schema.model_validate(parse_completion_json(response))
            except (LLMResponseError, ValidationError) as error:
                last_error = error
                if isinstance(error, LLMResponseError) and error.finish_reason == "length":
                    max_tokens = None  # let the endpoint use its own output limit on the retry
                logger.warning("unusable %s response (attempt %d): %s", task, attempt + 1, str(error)[:300])
                messages = messages[:2] + [
                    {"role": "assistant", "content": extract_chat_completion_text(response)[:4000]},
                    {"role": "user", "content": f"That reply was not valid: {str(error)[:800]}. Reply again with JSON only."},
                ]
        assert last_error is not None
        raise last_error

    async def complete_text(self, system: str, user: str, *, task: str, context: dict[str, Any]) -> str:
        response = await self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.5, max_tokens=self.max_tokens, json_mode=False,
        )
        return clean_chat_text(extract_chat_completion_text(response))

    async def research(self, system: str, user: str) -> tuple[str, list[dict[str, str]], bool]:
        # No live search in the Chat Completions format: the model answers from what it knows.
        note = (
            "\n\nYou have no web access. Use what you know, give your best realistic estimates, "
            "and mark anything that may be out of date."
        )
        text = await self.complete_text(system + note, user, task="research", context={})
        return text, [], False

    async def list_models(self) -> list[str]:
        page = await self.client.models.list()
        return sorted(m.id for m in page.data)

    async def aclose(self) -> None:
        await self.client.close()
