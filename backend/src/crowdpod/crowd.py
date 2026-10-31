"""Stage 3: every persona reacts to the idea, many personas per model call."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from .llm.base import LLMProvider
from .llm.json_utils import coerce_to_str
from .llm.mock import MockProvider
from .models import IdeaBrief, Persona, Reaction, ReactionBatch
from .vault import Vault

logger = logging.getLogger("crowdpod.crowd")

OnReaction = Callable[[Persona, Reaction], Awaitable[None]]
OnDegraded = Callable[[list[str], str], Awaitable[None]]


def brief_prompt(brief: IdeaBrief) -> str:
    price = "free" if brief.price_period == "free" or brief.price == 0 else (
        f"₹{brief.price:g} {'per ' + brief.price_period if brief.price_period != 'one_time' else 'one-time'}"
        + ("" if brief.one_time else f" (about ₹{brief.monthly_price:g} a month)")
    )
    return f"Product: {brief.name}\nCategory: {brief.category or 'unspecified'}\nPrice: {price}\n\n{brief.pitch}"


def _normalise(batch: ReactionBatch, personas: list[Persona], provider: str) -> list[Reaction]:
    """Match reactions to personas by id and check none are missing."""
    by_id = {r.persona_id: r for r in batch.reactions}
    missing = [p.id for p in personas if p.id not in by_id]
    if missing:
        raise ValueError(f"model skipped {len(missing)} personas, e.g. {missing[:3]}")
    out = []
    for p in personas:
        r = by_id[p.id]
        out.append(r.model_copy(update={
            "quote": coerce_to_str(r.quote), "top_objection": coerce_to_str(r.top_objection),
            "must_have": coerce_to_str(r.must_have), "provider": provider,
        }))
    return out


class CrowdRunner:
    def __init__(self, vault: Vault, provider: LLMProvider, *, batch_size: int = 20, concurrency: int = 4):
        self.vault = vault
        self.provider = provider
        self.fallback = MockProvider()
        self.batch_size = batch_size
        self.semaphore = asyncio.Semaphore(concurrency)

    async def _batch(self, brief: IdeaBrief, personas: list[Persona]) -> tuple[list[Reaction], str | None]:
        archetypes = self.vault.archetypes
        system = self.vault.template("crowd-batch")
        cards = "\n".join(p.card(archetypes[p.archetype_id], brief) for p in personas)
        user = f"{brief_prompt(brief)}\n\nThe people ({len(personas)}):\n{cards}"
        context = {"brief": brief, "personas": personas, "archetypes": archetypes}
        try:
            batch = await self.provider.complete_json(system, user, ReactionBatch, task="crowd", context=context)
            return _normalise(batch, personas, self.provider.name), None
        except Exception as error:  # one bad batch must not sink the run
            if self.provider is self.fallback:
                raise
            logger.warning("crowd batch failed, using offline answers: %s", error)
            batch = await self.fallback.complete_json(system, user, ReactionBatch, task="crowd", context=context)
            return _normalise(batch, personas, "mock-fallback"), str(error)[:300]

    async def run(
        self, brief: IdeaBrief, crowd: list[Persona], on_reaction: OnReaction, on_degraded: OnDegraded | None = None
    ) -> list[Reaction]:
        batches = [crowd[i : i + self.batch_size] for i in range(0, len(crowd), self.batch_size)]
        results: dict[str, Reaction] = {}

        async def one(batch: list[Persona]) -> None:
            async with self.semaphore:
                reactions, degraded = await self._batch(brief, batch)
            if degraded and on_degraded:
                await on_degraded([p.id for p in batch], degraded)
            for p, r in zip(batch, reactions):
                results[p.id] = r
                await on_reaction(p, r)

        await asyncio.gather(*(one(b) for b in batches))
        return [results[p.id] for p in crowd]
