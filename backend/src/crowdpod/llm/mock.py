"""Offline provider: deterministic answers computed from the persona's own data.

It is a rule-based stand-in for a model, used for tests, development and stage demos
without network. Results depend only on the persona seed and the inputs, so the same
run always gives the same crowd.
"""

from __future__ import annotations

import math
import random
import re
from typing import Any, TypeVar

from pydantic import BaseModel

from ..models import Archetype, HandsDecision, IdeaBrief, Observation, Persona, Reaction, ReactionBatch
from ..sampler import stable_seed
from .base import LLMProvider

T = TypeVar("T", bound=BaseModel)


def mentions(text: str, phrase: str) -> bool:
    """Whole-word, case-insensitive match ("app" does not match "happy"; "₹" matches "₹299")."""
    p = phrase.lower().strip()
    if not p:
        return False
    pattern = ("(?<!\\w)" if p[0].isalnum() else "") + re.escape(p) + ("(?:e?s)?(?!\\w)" if p[-1].isalnum() else "")
    return re.search(pattern, text.lower()) is not None


def _round10(x: float) -> int:
    return int(round(x / 10) * 10)


def react(persona: Persona, arch: Archetype, brief: IdeaBrief) -> Reaction:
    rng = random.Random(stable_seed(persona.seed, brief.name, brief.pitch, brief.price))
    text = brief.text()
    interests = [i for i in arch.interests if mentions(text, i)]
    pains = [p for p in arch.pains if mentions(text, p)]
    relevance = 1 - math.exp(-(len(interests) + 1.5 * len(pains)) / 2.5)
    # Two people in the same segment don't care equally; some just don't need it right now.
    fit = relevance * rng.uniform(0.35, 1.15)
    dealbreaker = next((d for d in arch.dealbreakers if any(mentions(text, w) for w in d.when)), None)

    price = brief.monthly_price
    budget = persona.budget_month
    affordable = 1.0 if price <= 0 else min(budget / price, 2.0) / 2
    over_budget = price > budget

    score = (
        0.50 * fit
        + 0.25 * affordable
        + 0.10 * persona.tech_comfort
        + 0.15 * persona.sentiment_bias
        + rng.gauss(0, 0.1)
        - (0.25 if dealbreaker else 0)
        - (0.15 * persona.price_sensitivity if over_budget else 0)
    )
    verdict = "adopt" if score >= 0.5 else "maybe" if score >= 0.3 else "reject"
    if verdict == "adopt" and price > budget * 1.2:
        verdict = "maybe"  # can't adopt what you can't afford

    share = max(0.0, min(1.0, 0.2 + 0.8 * fit - 0.3 * persona.price_sensitivity))
    wtp = _round10(budget * share * {"adopt": 1.0, "maybe": 0.6, "reject": 0.15}[verdict])
    if verdict == "adopt" and price > 0:
        wtp = max(wtp, _round10(price))  # an adopter accepts the asking price by definition

    if dealbreaker and verdict != "adopt":
        quote = dealbreaker.say
    else:
        lines = getattr(arch.voice, verdict) or ["Hmm."]
        quote = rng.choice(lines).replace("{product}", brief.name)

    if verdict == "adopt":
        objection = ""
    elif over_budget and rng.random() < 0.6:
        objection = "Too expensive for me"
    elif dealbreaker:
        objection = dealbreaker.say.split("?")[0].split(".")[0][:60]
    else:
        objection = rng.choice(arch.objections) if arch.objections else ""

    must = ""
    if arch.must_haves:
        must = arch.must_haves[0] if rng.random() < 0.6 else rng.choice(arch.must_haves)

    why = (
        f"Matches {', '.join((interests + pains)[:3])}" if interests or pains else "Nothing here speaks to my life"
    ) + (f"; ₹{price:g}/month vs my ₹{budget}" if price else "; it's free")
    return Reaction(
        persona_id=persona.id,
        verdict=verdict,
        willingness_to_pay=wtp,
        sentiment=max(-1.0, min(1.0, round(score * 2 - 0.8 + 0.3 * persona.sentiment_bias, 2))),
        quote=quote,
        top_objection=objection,
        must_have=must,
        reasoning=why,
        provider="mock",
    )


_STOP = set(
    "about after again also check could does find from have into just know like look make more much need "
    "only other over should site some than that their them then there these they this using want what when "
    "where whether which while will with would your yourself whole".split()
)


def goal_words(goal: str) -> list[str]:
    """Words from a free-text goal that could appear in a link or on the page."""
    words = re.findall(r"[a-z][a-z'-]{3,}", goal.lower())
    return list(dict.fromkeys(w for w in words if w not in _STOP))


def decide(persona: Persona, arch: Archetype, goal: str, obs: Observation, history: list[dict[str, Any]]) -> HandsDecision:
    rng = random.Random(stable_seed(persona.seed, "hands", len(history), obs.url, obs.scroll_y))
    # A goal set for this run says what to look for; otherwise use the archetype's own words.
    custom = goal not in arch.goals_on_site
    keywords = (goal_words(goal) if custom else []) or [k for k in arch.goal_keywords if k]
    clicked = {h.get("target_label", "").lower() for h in history if h.get("action") == "click"}
    moved = any(h.get("action") in ("click", "scroll") for h in history)

    def hit(label: str) -> str | None:
        return next((k for k in keywords if mentions(label, k)), None)

    # 1. A link or button that looks like the goal. People less at ease with tech miss some.
    for el in obs.elements:
        kw = hit(el["label"])
        if kw and el["label"].lower() not in clicked and rng.random() < 0.35 + 0.65 * persona.tech_comfort:
            return HandsDecision(thought=f'‘{el["label"]}’ — that should have the {kw}.', action="click", target=el["id"])

    # 2. The goal is on screen (in content, not just a menu link) after we did something to get here.
    content = obs.text
    for el in obs.elements:
        content = content.replace(el["label"], " ")
    found = next((k for k in keywords if mentions(content, k)), None)
    if found and moved:
        return HandsDecision(thought=f"Okay, found the {found}. That's what I needed.", action="done")

    # 3. Keep looking.
    if obs.scroll_y < obs.scroll_max:
        return HandsDecision(
            thought=rng.choice([f"Where is the {keywords[0]}? Scrolling.", "Still looking...", "Why is this page so long?"]),
            action="scroll", text="down",
        )
    return HandsDecision(thought=f"I can't find it. I wanted to {goal}. I'm leaving.", action="give_up")


class MockProvider(LLMProvider):
    name = "mock"

    async def complete_json(self, system: str, user: str, schema: type[T], *, task: str, context: dict[str, Any]) -> T:
        if task == "crowd":
            brief: IdeaBrief = context["brief"]
            archetypes: dict[str, Archetype] = context["archetypes"]
            batch = ReactionBatch(
                reactions=[react(p, archetypes[p.archetype_id], brief) for p in context["personas"]]
            )
            return schema.model_validate(batch.model_dump())
        if task == "hands":
            decision = decide(context["persona"], context["archetype"], context["goal"], context["observation"], context["history"])
            return schema.model_validate(decision.model_dump())
        raise ValueError(f"mock provider has no JSON task {task!r}")

    async def complete_text(self, system: str, user: str, *, task: str, context: dict[str, Any]) -> str:
        if task == "architect":
            from ..architect import offline_document

            return offline_document(context["doc"], context["brief"], context["summary"], context["quotes"])
        if task == "interview":
            persona: Persona = context["persona"]
            arch: Archetype = context["archetype"]
            rng = random.Random(stable_seed(persona.seed, "interview", context["question"]))
            pool = arch.voice.maybe + arch.voice.reject or ["I don't know."]
            return rng.choice(pool).replace("{product}", context.get("product", "it"))
        raise ValueError(f"mock provider has no text task {task!r}")
