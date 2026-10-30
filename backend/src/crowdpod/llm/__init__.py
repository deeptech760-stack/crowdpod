from __future__ import annotations

from ..runtime import BrainSettings
from .base import LLMProvider
from .mock import MockProvider


def make_provider(brain: BrainSettings) -> LLMProvider:
    """A fresh client for one run or request; the caller closes it with aclose()."""
    if brain.provider == "mock":
        return MockProvider()
    brain.check_ready()
    if brain.provider == "anthropic":
        from .anthropic_provider import AnthropicProvider

        # base_url is left empty for the official endpoint; tests point it at a local fake
        return AnthropicProvider(api_key=brain.api_key, model=brain.model, base_url=brain.base_url, effort=brain.effort)
    from .openai_compat import OpenAICompatProvider

    return OpenAICompatProvider(base_url=brain.base_url, api_key=brain.api_key, model=brain.model)


__all__ = ["LLMProvider", "MockProvider", "make_provider"]
