"""Stage 5: turn the crowd's numbers and quotes into a BRD and a PRD."""

from __future__ import annotations

import asyncio
from typing import Any

from .aggregate import plural
from .crowd import brief_prompt
from .llm.base import LLMProvider
from .models import CrowdSummary, Documents, IdeaBrief, Persona, Reaction
from .vault import Vault, render

BRD_OUTLINE = """Sections: # Business Requirements: <product>
## Summary (3 sentences) ## Market: who the crowd says the customer is (segment table)
## Pricing (price vs willingness to pay) ## Risks (top objections) ## Ask real people next"""

PRD_OUTLINE = """Sections: # Product Requirements: <product>
## Target user ## Problem ## MVP scope (ordered by how many asked for it)
## Not in the MVP ## Success metrics ## Ask real people next"""


def pick_quotes(crowd: list[Persona], reactions: list[Reaction], per_segment: int = 3) -> list[dict[str, Any]]:
    """For each segment, the strongest adopt, maybe and reject quote."""
    best: dict[tuple[str, str], tuple[Persona, Reaction]] = {}
    for p, r in zip(crowd, reactions):
        if not r.quote:
            continue
        key = (p.archetype_id, r.verdict)
        if key not in best or abs(r.sentiment) > abs(best[key][1].sentiment):
            best[key] = (p, r)
    out = []
    for (arch, verdict), (p, r) in sorted(best.items()):
        out.append({"segment": arch, "verdict": verdict, "name": p.name, "age": p.age, "quote": r.quote})
    return out


def summary_table(s: CrowdSummary) -> str:
    rows = ["| Segment | People | Adopt | Interested | Median ₹/month | Budget covers price |", "|---|---|---|---|---|---|"]
    for seg in s.segments:
        rows.append(
            f"| {seg.label} | {seg.count} | {seg.adoption_rate:.0%} | {seg.interest_rate:.0%} | "
            f"{seg.median_wtp:g} | {seg.price_fit_rate:.0%} |"
        )
    return "\n".join(rows)


def _facts(brief: IdeaBrief, s: CrowdSummary, quotes: list[dict[str, Any]]) -> str:
    q = "\n".join(f'- {x["name"]}, {x["age"]} ({x["segment"]}, {x["verdict"]}): "{x["quote"]}"' for x in quotes)
    objections = "\n".join(f"- {t} ({n})" for t, n in s.top_objections)
    wants = "\n".join(f"- {t} ({n})" for t, n in s.top_must_haves)
    return (
        f"{brief_prompt(brief)}\nFounder's intended audience: {brief.target_hint or 'not stated'}\n\n"
        f"Crowd: {s.size} people. Adoption {s.adoption_rate:.0%}, interested {s.interest_rate:.0%}, "
        f"median willingness to pay ₹{s.median_wtp:g}/month (₹{s.median_wtp_interested:g} among those interested), budget covers price for {s.price_fit_rate:.0%}.\n"
        f"Headline: {s.headline}\n\n{summary_table(s)}\n\nTop objections:\n{objections}\n\n"
        f"Most requested:\n{wants}\n\nQuotes:\n{q}"
    )


def _questions(brief: IdeaBrief, s: CrowdSummary) -> list[str]:
    seg = next((x for x in s.segments if x.archetype_id == s.best_segment), None)
    who = plural(seg.label) if seg else "people in your target market"
    qs = [f"Tell me about the last time you tried to solve this problem. What did you use, and what did it cost?"]
    if s.top_must_haves:
        qs.append(f'How do you handle "{s.top_must_haves[0][0]}" today? Would you pay to have it done for you?')
    if s.top_objections:
        qs.append(f'Simulated {who} said "{s.top_objections[0][0]}". Is that true for you? Why?')
    qs.append(f"What would make you stop using {brief.name} after the first week?")
    return [f"Ask {who}: {q}" for q in qs]


def offline_document(doc: str, brief: IdeaBrief, s: CrowdSummary, quotes: list[dict[str, Any]]) -> str:
    """Fixed templates filled from the numbers; used by the offline provider."""
    seg = next((x for x in s.segments if x.archetype_id == s.best_segment), None)
    ask = "\n".join(f"{i}. {q}" for i, q in enumerate(_questions(brief, s), 1))
    wants = [t for t, _ in s.top_must_haves]
    note = "_Simulated crowd. Confirm with real interviews before building._"
    if doc == "brd":
        risks = "\n".join(f"- **{t}** (said by {n})" for t, n in s.top_objections) or "- None stood out."
        seg_quotes = "\n".join(f'> "{q["quote"]}" — {q["name"]}, {q["age"]}' for q in quotes if seg and q["segment"] == seg.archetype_id)
        return (
            f"# Business Requirements: {brief.name}\n\n{note}\n\n## Summary\n{s.headline} "
            f"Across all {s.size} people, {s.adoption_rate:.0%} would adopt and {s.interest_rate:.0%} are at least interested. "
            f"Those interested would pay a median of ₹{s.median_wtp_interested:g} a month against an asking price of ₹{s.monthly_price:g}.\n\n"
            f"## Market\n{summary_table(s)}\n\n" + (f"What the strongest segment says:\n\n{seg_quotes}\n\n" if seg_quotes else "")
            + f"## Pricing\nThe price fits the monthly budget of {s.price_fit_rate:.0%} of the crowd"
            + (f" and {seg.price_fit_rate:.0%} of {plural(seg.label)}. Their median willingness to pay is ₹{seg.median_wtp:g}." if seg else ".")
            + f"\n\n## Risks\n{risks}\n\n## Ask real people next\n{ask}\n"
        )
    if doc == "prd":
        scope = "\n".join(f"{i}. {t} — requested by {n}" for i, (t, n) in enumerate(s.top_must_haves, 1)) or "1. Core flow only."
        later = ", ".join(wants[3:]) or "everything not listed above"
        target = f"{seg.label} ({seg.count} of {s.size} in the crowd, {seg.adoption_rate:.0%} adoption)" if seg else "Not found yet."
        return (
            f"# Product Requirements: {brief.name}\n\n{note}\n\n## Target user\n{target}\n\n"
            f"## Problem\n{brief.pitch}\n\n## MVP scope\n{scope}\n\n## Not in the MVP\n{later}.\n\n"
            f"## Success metrics\n- Adoption among {plural(seg.label) if seg else 'target users'} in real interviews close to the simulated {seg.adoption_rate if seg else s.adoption_rate:.0%}\n"
            f"- A first-time visitor finds the price in under 10 seconds\n- Week-1 retention above 40%\n\n"
            f"## Ask real people next\n{ask}\n"
        )
    raise ValueError(f"unknown document {doc!r}")


class Architect:
    def __init__(self, vault: Vault, provider: LLMProvider):
        self.vault = vault
        self.provider = provider

    async def write(self, brief: IdeaBrief, summary: CrowdSummary, crowd: list[Persona], reactions: list[Reaction]) -> Documents:
        quotes = pick_quotes(crowd, reactions)
        facts = _facts(brief, summary, quotes)

        async def one(doc: str, outline: str) -> str:
            system = render(self.vault.template("architect"), {"doc": doc.upper(), "doc_outline": outline})
            context = {"doc": doc, "brief": brief, "summary": summary, "quotes": quotes}
            return await self.provider.complete_text(system, facts, task="architect", context=context)

        brd, prd = await asyncio.gather(one("brd", BRD_OUTLINE), one("prd", PRD_OUTLINE))
        return Documents(brd_md=brd, prd_md=prd)
