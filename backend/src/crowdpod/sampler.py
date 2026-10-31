"""Builds a reproducible crowd from archetype ranges."""

from __future__ import annotations

import hashlib
import random

from .models import Archetype, Persona
from .vault import Vault


def stable_seed(*parts: object) -> int:
    """A seed that is the same on every machine and Python run (unlike hash())."""
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def allocate(size: int, weights: dict[str, float]) -> dict[str, int]:
    """Split `size` across keys in proportion to weights (largest remainder, exact total)."""
    weights = {k: w for k, w in weights.items() if w > 0}
    if not weights:
        raise ValueError("mix has no positive weights")
    total = sum(weights.values())
    raw = {k: size * w / total for k, w in weights.items()}
    counts = {k: int(v) for k, v in raw.items()}
    leftover = size - sum(counts.values())
    for k in sorted(raw, key=lambda k: (raw[k] - counts[k], k), reverse=True)[:leftover]:
        counts[k] += 1
    return counts


def _uniform(rng: random.Random, r: tuple[float, float]) -> float:
    lo, hi = r
    return rng.uniform(lo, hi) if hi > lo else lo


def sample_persona(arch: Archetype, run_seed: int, index: int, run_id: str) -> Persona:
    seed = stable_seed(run_seed, arch.id, index)
    rng = random.Random(seed)
    gender = arch.gender if arch.gender != "any" else rng.choice(["female", "male"])
    budget = _uniform(rng, arch.budget_month)
    persona = Persona(
        id=f"{run_id}-{arch.id}-{index}",
        archetype_id=arch.id,
        seed=seed,
        name=rng.choice(arch.names),
        age=round(_uniform(rng, arch.age)),
        gender=gender,
        profession=arch.profession,
        city=arch.city,
        mbti=rng.choice(arch.mbti) if arch.mbti else "",
        mood=rng.choice(arch.moods),
        device=rng.choice(arch.devices),
        budget_month=int(round(budget / 10) * 10),
        patience_seconds=round(_uniform(rng, arch.patience_seconds)),
        tech_comfort=round(_uniform(rng, arch.tech_comfort), 2),
        price_sensitivity=round(_uniform(rng, arch.price_sensitivity), 2),
        sentiment_bias=round(_uniform(rng, arch.sentiment_bias), 2),
    )
    # drawn last, so adding it didn't change any persona an older seed produced
    lo, hi = arch.purchase_budget
    purchase = _uniform(rng, (lo, hi) if hi > 0 else (arch.budget_month[0] * 12, arch.budget_month[1] * 12))
    return persona.model_copy(update={"purchase_budget": int(round(purchase / 100) * 100)})


class CrowdSampler:
    def __init__(self, vault: Vault, seed: int, archetypes: dict[str, Archetype] | None = None):
        self.vault = vault
        self.seed = seed
        # a run can bring its own archetypes (generated for the idea); default is the vault's
        self.archetypes = archetypes if archetypes is not None else vault.archetypes

    def sample(self, size: int, run_id: str, mix: dict[str, float] | None = None) -> list[Persona]:
        archetypes = self.archetypes
        if mix:
            unknown = set(mix) - set(archetypes)
            if unknown:
                raise ValueError(f"unknown archetypes in mix: {sorted(unknown)}")
            weights = mix
        else:
            weights = {a.id: a.weight for a in archetypes.values()}
        crowd: list[Persona] = []
        for arch_id, count in allocate(size, weights).items():
            arch = archetypes[arch_id]
            crowd.extend(sample_persona(arch, self.seed, i, run_id) for i in range(count))
        # interleave segments so a live view does not fill one archetype at a time
        random.Random(stable_seed(self.seed, "order")).shuffle(crowd)
        return crowd
