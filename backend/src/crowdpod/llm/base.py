"""The interface every model provider implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    """`task` names the pipeline step ("crowd", "architect", "hands", "interview").

    `context` carries the structured inputs behind the prompt. A real model reads the
    prompts; the offline provider reads `context`, so both answer the same question.
    """

    name: str = "base"

    @abstractmethod
    async def complete_json(
        self, system: str, user: str, schema: type[T], *, task: str, context: dict[str, Any]
    ) -> T: ...

    @abstractmethod
    async def complete_text(self, system: str, user: str, *, task: str, context: dict[str, Any]) -> str: ...

    async def research(self, system: str, user: str) -> tuple[str, list[dict[str, str]], bool]:
        """Free-text market research. Returns (text, sources as {url, title}, grounded),
        where grounded means it came from a live web search rather than the model's memory."""
        raise NotImplementedError(f"the {self.name} brain can't research a market")

    async def aclose(self) -> None:
        return None
