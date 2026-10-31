"""Stage 1: research the idea's market and design personas for it, then save them to the vault.

The handwritten archetypes describe one kind of crowd. A real idea needs the people of its own
market: for a foldable phone, Apple upgraders, foldable owners and creative professionals, with
budgets that match what they actually spend. The brain researches first and builds the audience
from what it found, and every generated persona is kept as a note in the Obsidian vault.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from .crowd import brief_prompt
from .hands.driver import VIEWPORTS
from .llm.base import LLMProvider
from .llm.mock import goal_words
from .models import Archetype, Audience, DescribedAudience, GeneratedPersona, IdeaBrief, Research, Source, Voice
from .vault import Vault, render


class AudienceUnavailable(Exception):
    """The current brain can't research or design personas (the offline brain)."""


class ResearchDigest(BaseModel):
    summary: str
    facts: list[str]
    price_points: list[str]
    buyer_segments: list[str]


def slug(text: str, limit: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit].strip("-") or "persona"


def _range(r: tuple[float, float], lo: float, hi: float) -> tuple[float, float]:
    a, b = sorted((max(lo, min(hi, r[0])), max(lo, min(hi, r[1]))))
    return (a, b)


def to_archetype(p: GeneratedPersona, brief: IdeaBrief, taken: set[str], prefix: str = "gen-") -> Archetype:
    """Turn the brain's design into a regular archetype, with values kept in sane bounds."""
    base = prefix + slug(p.id or p.label, 30)
    aid, n = base, 2
    while aid in taken:
        aid, n = f"{base}-{n}", n + 1
    taken.add(aid)
    devices = [d for d in p.devices if d in VIEWPORTS] or ["mid-android"]
    quotes = [q.replace(brief.name, "{product}") for q in p.sample_quotes] or ["Hmm."]
    keywords = list(dict.fromkeys(w for g in p.goals_on_site for w in goal_words(g))) or ["price", "pricing"]
    body = (
        f"## Who I am\n{p.who_they_are}\n\n## How I decide\n{p.how_they_decide}\n\n"
        "## Reasons I say no\n" + "\n".join(f"- {o}" for o in p.objections) + f"\n\n## How I talk\n{p.how_they_talk}"
    )
    return Archetype(
        id=aid,
        label=p.label[:60],
        weight=max(p.share, 0.02),
        names=p.names[:12],
        age=_range(p.age, 14, 90),
        profession=p.profession,
        city=p.city or "India",
        budget_month=_range(p.budget_month, 0, 1_000_000),
        purchase_budget=_range(p.purchase_budget, 0, 100_000_000),
        patience_seconds=_range(p.patience_seconds, 5, 300),
        tech_comfort=_range(p.tech_comfort, 0, 1),
        price_sensitivity=_range(p.price_sensitivity, 0, 1),
        sentiment_bias=_range(p.sentiment_bias, -1, 1),
        moods=p.moods or ["neutral"],
        devices=devices,
        interests=[i.lower() for i in p.interests],
        pains=[i.lower() for i in p.pains],
        objections=p.objections,
        goals_on_site=p.goals_on_site or ["find the price"],
        goal_keywords=keywords,
        must_haves=p.must_haves,
        voice=Voice(adopt=quotes, maybe=quotes, reject=quotes),
        body=body,
        generated_for=brief.name,
        evidence=p.evidence,
    )


def write_note(arch: Archetype, folder: Path, root: Path, research: Research) -> str:
    """Save a generated archetype as an Obsidian note, in the same format as the handwritten ones."""
    folder.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {"type": "archetype", **arch.model_dump(exclude={"body", "source"})}
    meta["voice"] = {"sample": arch.voice.adopt}
    meta["sources"] = [s.url for s in research.sources]
    path = folder / f"{arch.id}.md"
    front = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=1000)
    path.write_text(f"---\n{front}---\n{arch.body}\n", encoding="utf-8")
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


async def build_audience(
    vault: Vault, provider: LLMProvider, brief: IdeaBrief, *, count: int, notes: str, out_dir: Path | None, run_id: str
) -> tuple[Research, dict[str, Archetype]]:
    idea = brief_prompt(brief) + (f"\nThe founder thinks it's for: {brief.target_hint}" if brief.target_hint else "")
    if notes:
        idea += f"\n\nWhat the founder already knows about the market:\n{notes}"

    try:
        text, sources, grounded = await provider.research(vault.template("research"), idea)
    except NotImplementedError as e:
        raise AudienceUnavailable(str(e)) from e
    if not text:
        raise ValueError("the research came back empty")

    digest = await provider.complete_json(
        "Condense this market research into JSON: a 2-3 sentence summary, concrete facts with numbers, "
        "price points of comparable products, and the buyer segments it identifies. Reply with JSON only.",
        text, ResearchDigest, task="research_digest", context={},
    )
    research = Research(
        **digest.model_dump(), sources=[Source(**s) for s in sources[:20]], grounded=grounded,
    )

    audience = await provider.complete_json(
        render(vault.template("audience"), {"count": count}),
        f"{idea}\n\nResearch:\n{text}",
        Audience, task="audience", context={},
    )
    return research, adopt_audience(vault, brief, audience, research, out_dir=out_dir, run_id=run_id, count=count)


async def describe_personas(
    vault: Vault, provider: LLMProvider, brief: IdeaBrief, descriptions: list[str], *, research: Research | None,
    out_dir: Path | None, run_id: str,
) -> dict[str, Archetype]:
    """Full personas for the people the user described, one segment each."""
    facts = ""
    if research and research.summary:
        facts = f"\n\nMarket research so far:\n{research.summary}\n" + "\n".join(f"- {f}" for f in research.facts[:15])
    people = "\n".join(f"{i + 1}. <<<{d}>>>" for i, d in enumerate(descriptions))
    designed = await provider.complete_json(
        render(vault.template("persona-from-brief"), {"count": len(descriptions)}),
        f"{brief_prompt(brief)}{facts}\n\nPeople the founder described:\n{people}",
        DescribedAudience, task="describe", context={"descriptions": descriptions, "brief": brief, "vault": vault},
    )
    personas = designed.personas[: len(descriptions)]
    for p, text in zip(personas, descriptions):  # keep the user's own words with the persona
        mark = f"Described by the user: {text}"
        if mark not in p.evidence:
            p.evidence.insert(0, mark)
    return adopt_audience(vault, brief, Audience.model_construct(personas=personas),
                          research or Research(summary="Personas described by the user."),
                          out_dir=out_dir, run_id=run_id, count=len(personas), prefix="you-")


def adopt_audience(
    vault: Vault, brief: IdeaBrief, audience: Audience, research: Research, *, out_dir: Path | None, run_id: str,
    count: int = 10, prefix: str = "gen-",
) -> dict[str, Archetype]:
    """Turn designed personas into archetypes and save each one as a vault note."""
    taken = set(vault.archetypes)
    generated: dict[str, Archetype] = {}
    for p in audience.personas[:count]:
        arch = to_archetype(p, brief, taken, prefix)
        if out_dir is not None:  # no notes on a public server: the personas live in the run itself
            folder = out_dir / f"{slug(brief.name)}-{run_id}"
            arch = arch.model_copy(update={"source": write_note(arch, folder, vault.root, research)})
        generated[arch.id] = arch
    return generated
