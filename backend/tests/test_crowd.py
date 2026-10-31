from __future__ import annotations

import pytest

from crowdpod.aggregate import summarise, top_phrases
from crowdpod.architect import Architect
from crowdpod.crowd import CrowdRunner
from crowdpod.llm.base import LLMProvider
from crowdpod.llm.json_utils import LLMResponseError, parse_json_object
from crowdpod.llm.mock import MockProvider, goal_words, mentions
from crowdpod.models import ReactionBatch
from crowdpod.sampler import CrowdSampler, allocate
from crowdpod.vault import render


def test_vault_loads_all_archetypes(vault):
    assert set(vault.archetypes) == {
        "athlete", "auto-driver", "ceo", "corporate-worker", "dancer", "househusband", "mother",
        "placement-officer", "recruiter", "student",
    }
    for a in vault.archetypes.values():
        assert a.body.startswith("## Who I am"), a.id
        assert a.voice.adopt and a.voice.reject, a.id


def test_persona_system_prompt_is_filled(vault):
    p = CrowdSampler(vault, seed=1).sample(1, "t", {"mother": 1})[0]
    prompt = vault.persona_system_prompt(p)
    assert p.name in prompt and "{{" not in prompt and "Reasons I say no" in prompt


def test_render_rejects_unknown_placeholder():
    with pytest.raises(KeyError):
        render("hi {{who}}", {})


def test_allocate_is_exact_and_proportional():
    counts = allocate(101, {"a": 1, "b": 1, "c": 2})
    assert sum(counts.values()) == 101 and counts["c"] in (50, 51)


def test_sampling_is_reproducible(vault):
    a = CrowdSampler(vault, seed=42).sample(300, "x")
    b = CrowdSampler(vault, seed=42).sample(300, "x")
    c = CrowdSampler(vault, seed=43).sample(300, "x")
    assert [p.model_dump() for p in a] == [p.model_dump() for p in b]
    assert [p.model_dump() for p in a] != [p.model_dump() for p in c]
    assert len({p.id for p in a}) == 300


def test_goal_words_drop_filler():
    assert goal_words("Check whether this is the official college site") == ["official", "college"]


def test_mentions_whole_words_and_symbols():
    assert mentions("A fitness app", "app")
    assert not mentions("be happy", "app")
    assert mentions("only ₹299 a month", "₹")


def test_parse_json_object_accepts_fences_and_rejects_garbage():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('{"a": 1} hope that helps') == {"a": 1}
    with pytest.raises(LLMResponseError):
        parse_json_object("[1, 2]")
    with pytest.raises(LLMResponseError):
        parse_json_object('{"a": 1} {"b": 2}')


def test_top_phrases_merges_variants():
    assert top_phrases(["Too expensive", "too expensive.", "No time"]) [0] == ("Too expensive", 2)


async def test_pitch_story_fitness_app(vault, brief):
    """The pitch's example: a fitness app for athletes turns out to be for tired corporate workers."""
    crowd = CrowdSampler(vault, seed=7).sample(400, "t")
    seen = []

    async def on_reaction(p, r):
        seen.append(r.persona_id)

    reactions = await CrowdRunner(vault, MockProvider(), batch_size=20).run(brief, crowd, on_reaction)
    assert len(reactions) == len(seen) == 400
    assert [r.persona_id for r in reactions] == [p.id for p in crowd]

    s = summarise(brief, crowd, reactions, vault.archetypes)
    assert s.best_segment == "corporate-worker", s.segments
    assert s.headline.startswith("Your market isn't athletes")
    seg = {x.archetype_id: x for x in s.segments}
    assert seg["mother"].adoption_rate < seg["corporate-worker"].adoption_rate
    mother_quotes = {r.quote for p, r in zip(crowd, reactions) if p.archetype_id == "mother"}
    assert "Twenty minutes a day? I haven't had twenty minutes since 2009." in mother_quotes

    docs = await Architect(vault, MockProvider()).write(brief, s, crowd, reactions)
    assert docs.brd_md.startswith("# Business Requirements: FitDesk")
    assert "Ask real people next" in docs.brd_md and "Ask real people next" in docs.prd_md
    assert "Outlook and Google Calendar sync" in docs.prd_md


class _BrokenProvider(LLMProvider):
    name = "broken"

    async def complete_json(self, system, user, schema, *, task, context):
        return ReactionBatch(reactions=[])  # skips everyone

    async def complete_text(self, system, user, *, task, context):
        return ""


async def test_bad_batch_falls_back_and_is_reported(vault, brief):
    crowd = CrowdSampler(vault, seed=1).sample(30, "t")
    degraded = []

    async def on_reaction(p, r):
        pass

    async def on_degraded(ids, err):
        degraded.append((len(ids), err))

    reactions = await CrowdRunner(vault, _BrokenProvider(), batch_size=20).run(brief, crowd, on_reaction, on_degraded)
    assert len(reactions) == 30 and all(r.provider == "mock-fallback" for r in reactions)
    assert sorted(n for n, _ in degraded) == [10, 20] and "skipped" in degraded[0][1]


def test_goal_words_keep_short_specific_words():
    assert goal_words("find the iPhone Duo and its price") == ["iphone", "duo", "price"]


def test_brain_prefers_specific_links_and_sees_prices():
    """'Duo' beats the everywhere-word 'iPhone', and an amount on screen counts as the price."""
    from crowdpod.llm.mock import decide
    from crowdpod.models import Observation

    p = CrowdSampler(vault := __import__("crowdpod.vault", fromlist=["Vault"]).Vault(
        __import__("crowdpod.config", fromlist=["ROOT"]).ROOT / "vault"), seed=1).sample(1, "t", {"student": 1})[0]
    p = p.model_copy(update={"tech_comfort": 1.0})
    arch = vault.archetypes["student"]
    goal = "find the iPhone Duo and its price"
    links = [{"id": f"e{i}", "role": "link", "label": l} for i, l in enumerate(
        ["iPhone", "Shop iPhone", "iPhone 18 Pro", "iPhone Accessories", "Learn more, iPhone Duo"])]
    home = Observation(url="https://x/in/", title="Home", scroll_y=0, scroll_max=2000, text="Welcome", elements=links)
    d = decide(p, arch, goal, home, [])
    assert d.action == "click" and d.target == "e4", d

    # the product page shows the name and an amount: done, even though the word "price" isn't there
    page = Observation(url="https://x/in/iphone-duo/", title="iPhone Duo", scroll_y=0, scroll_max=2000,
                       text="iPhone Shop iPhone iPhone Duo Hello, hello. From ₹299900.00 or ₹26574.00/mo.",
                       content="iPhone Duo Hello, hello. From ₹299900.00 or ₹26574.00/mo.", elements=links[:2])
    assert decide(p, arch, goal, page, [{"action": "click", "target_label": "Learn more, iPhone Duo"}]).action == "done"

    # a page that only says "iPhone" is not success for this goal
    other = Observation(url="https://x/in/iphone/", title="iPhone", scroll_y=0, scroll_max=0,
                        text="iPhone 18 Pro. From ₹1,49,900.", elements=[])
    assert decide(p, arch, goal, other, [{"action": "scroll"}]).action == "give_up"
