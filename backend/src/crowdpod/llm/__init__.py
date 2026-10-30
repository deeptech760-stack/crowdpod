from __future__ import annotations

from ..config import Settings
from .base import LLMProvider
from .mock import MockProvider


def get_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockProvider()
    if settings.llm_provider == "openai":
        from .openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(
            base_url=settings.llm_base_url, api_key=settings.llm_api_key, model=settings.llm_model
        )
    raise ValueError(f"unknown CROWDPOD_LLM_PROVIDER {settings.llm_provider!r} (use 'mock' or 'openai')")


__all__ = ["LLMProvider", "MockProvider", "get_provider"]
