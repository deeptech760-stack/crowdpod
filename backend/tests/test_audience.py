"""Research and generated personas: the crowd is built for the idea, with realistic budgets."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from crowdpod.aggregate import summarise
from crowdpod.api import create_app
from crowdpod.models import IdeaBrief
from crowdpod.sampler import CrowdSampler
from crowdpod.vault import split_note

from .fake_llm import FakeLLM

BROWSER = {"show_windows": False, "slow_mo_ms": 0, "parallel": 1}
PHONE = {"name": "Apple iPhone Duo", "pitch": "A foldable iPhone with two screens that opens into a small tablet.",
         "category": "smartphone", "price": 189900, "price_period": "one_time", "target_hint": "tech enthusiasts"}


@pytest.fixture
def fake_llm():
    server = FakeLLM()
    yield server
    server.close()


def _brain(fake: FakeLLM):
    return {"provider": "openai", "base_url": fake.base_url, "model": "fake-small", "concurrency": 2, "batch_size": 10}


def _events(client, run_id):
    with client.stream("GET", f"/api/runs/{run_id}/events") as resp:
        return [line[7:] for line in resp.iter_lines() if line.startswith("event: ")]


def test_generated_audience_end_to_end(settings, fake_llm):
    with TestClient(create_app(settings)) as client:
        client.put("/api/settings", json={"brain": _brain(fake_llm), "browser": BROWSER})
        run_id = client.post("/api/runs", json={"brief": PHONE, "crowd_size": 30}).json()["run_id"]
        events = _events(client, run_id)
        assert events[:4] == ["run.started", "research.started", "research.done", "audience.created"]
        assert events[-1] == "run.finished"

        audience = client.get(f"/api/runs/{run_id}/audience").json()
        assert audience["research"]["grounded"] is False  # no live search on an OpenAI-compatible brain
        assert audience["research"]["price_points"] == ["Fake foldable: ₹1,64,999"]
        labels = {p["label"] for p in audience["personas"]}
        assert labels == {"Apple upgrader", "Foldable owner", "Budget switcher"}
        # unknown devices are dropped instead of breaking the browser agents
        assert all(set(p["devices"]) <= {"iphone", "mid-android"} for p in audience["personas"])

        rows = client.get(f"/api/runs/{run_id}/reactions", params={"limit": 100}).json()
        assert len(rows) == 30 and all(r["persona"]["archetype_id"].startswith("gen-") for r in rows)

        summary = client.get(f"/api/runs/{run_id}").json()["summary"]
        assert summary["price_unit"] == "one_time" and summary["monthly_price"] == 189900
        # Apple upgraders (₹1.2-2 lakh) can sometimes afford it; budget switchers (₹15-40k) never can
        fit = {s["label"]: s["price_fit_rate"] for s in summary["segments"]}
        assert fit["Budget switcher"] == 0 and fit["Apple upgrader"] > 0

        pid = rows[0]["persona"]["id"]
        assert client.post(f"/api/runs/{run_id}/personas/{pid}/interview", json={"question": "Why?"}).status_code == 200

    notes = list((settings.generated_dir).rglob("*.md"))
    assert len(notes) == 3
    meta, body = split_note(notes[0].read_text(encoding="utf-8"))
    assert meta["type"] == "archetype" and meta["generated_for"] == "Apple iPhone Duo"
    assert body.startswith("## Who I am") and "## Reasons I say no" in body


def test_both_mixes_generated_and_builtin(settings, fake_llm):
    with TestClient(create_app(settings)) as client:
        client.put("/api/settings", json={"brain": _brain(fake_llm), "browser": BROWSER})
        run_id = client.post("/api/runs", json={"brief": PHONE, "crowd_size": 60, "audience": "both"}).json()["run_id"]
        assert _events(client, run_id)[-1] == "run.finished"
        ids = {r["persona"]["archetype_id"] for r in client.get(f"/api/runs/{run_id}/reactions", params={"limit": 500}).json()}
        assert any(i.startswith("gen-") for i in ids) and any(not i.startswith("gen-") for i in ids)


def test_offline_brain_falls_back_to_builtin(settings):
    with TestClient(create_app(settings)) as client:
        run_id = client.post("/api/runs", json={"brief": PHONE, "crowd_size": 20}).json()["run_id"]
        events = _events(client, run_id)
        assert "audience.skipped" in events and "audience.created" not in events and events[-1] == "run.finished"
        rows = client.get(f"/api/runs/{run_id}/reactions").json()
        assert not any(r["persona"]["archetype_id"].startswith("gen-") for r in rows)


def test_one_time_prices_use_purchase_budgets(vault):
    """A ₹40,000 phone fits many corporate workers' purchase budgets, though never their monthly app budget."""
    brief = IdeaBrief(name="Phone", pitch="A mid-range phone with a great camera.", price=40000, price_period="one_time")
    crowd = CrowdSampler(vault, seed=3).sample(200, "t", {"corporate-worker": 1})
    assert all(p.purchase_budget >= 30000 for p in crowd)
    from crowdpod.llm.mock import react

    reactions = [react(p, vault.archetypes[p.archetype_id], brief) for p in crowd]
    s = summarise(brief, crowd, reactions, vault.archetypes)
    assert s.price_unit == "one_time" and 0.5 < s.price_fit_rate < 1
    assert "one-time" in s.headline or s.best_segment is None


def test_extended_vault_leaves_the_base_alone(vault):
    from crowdpod.models import Archetype

    extra = Archetype(id="gen-x", label="X", names=["A"], age=(20, 30), profession="p", budget_month=(0, 1),
                      patience_seconds=(10, 20), tech_comfort=(0, 1), price_sensitivity=(0, 1),
                      sentiment_bias=(0, 0), moods=["m"], devices=["laptop"])
    view = vault.extended({"gen-x": extra})
    assert "gen-x" in view.archetypes and "gen-x" not in vault.archetypes


def test_supplied_personas_work_without_a_model(settings):
    """An MCP client that did its own research can hand Crowdpod the personas; no API key needed."""
    from .fake_llm import FAKE_AUDIENCE

    req = {"brief": PHONE, "crowd_size": 30, "provided_audience": FAKE_AUDIENCE,
           "provided_research": {"summary": "Researched by the client.", "facts": ["Foldables start at ₹1.5 lakh"],
                                 "sources": [{"url": "https://example.com/foldables"}], "grounded": True}}
    with TestClient(create_app(settings)) as client:  # offline brain
        run_id = client.post("/api/runs", json=req).json()["run_id"]
        events = _events(client, run_id)
        assert "audience.created" in events and "audience.skipped" not in events and events[-1] == "run.finished"
        audience = client.get(f"/api/runs/{run_id}/audience").json()
        assert audience["research"]["grounded"] and len(audience["personas"]) == 3
        rows = client.get(f"/api/runs/{run_id}/reactions", params={"limit": 100}).json()
        assert all(r["persona"]["archetype_id"].startswith("gen-") for r in rows)
    assert len(list(settings.generated_dir.rglob("*.md"))) == 3


def test_described_people_with_a_model(settings, fake_llm):
    """A model brain writes the described personas; the user's own words stay in their evidence."""
    with TestClient(create_app(settings)) as client:
        client.put("/api/settings", json={"brain": _brain(fake_llm), "browser": BROWSER})
        people = ["A broke student in Pune", "A busy doctor in Delhi who hates long forms"]
        run = client.post("/api/runs", json={"brief": PHONE, "crowd_size": 30, "described": people}).json()["run_id"]
        assert _events(client, run)[-1] == "run.finished"
        personas = client.get(f"/api/runs/{run}/audience").json()["personas"]
        described = [p for p in personas if p["id"].startswith("you-")]
        assert [p["label"] for p in described] == ["Described 0", "Described 1"]  # written by the model
        assert [p["evidence"][0] for p in described] == [f"Described by the user: {d}" for d in people]
        assert len(personas) == 3 + 2  # the researched audience plus the described people
