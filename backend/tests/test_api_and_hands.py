from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from crowdpod.api import create_app
from crowdpod.events import EventBus
from crowdpod.hands.agent import run_session
from crowdpod.hands.driver import PlaywrightBrowser
from crowdpod.llm.mock import MockProvider
from crowdpod.models import HandsRequest, HandsStep, RunRequest
from crowdpod.pipeline import Pipeline
from crowdpod.runtime import SettingsStore, defaults_from
from crowdpod.sampler import CrowdSampler
from crowdpod.store import Store


def _persona(vault, archetype, seed=7):
    return CrowdSampler(vault, seed=seed).sample(1, "h", {archetype: 1})[0]


async def _session(vault, tmp_path, url, archetype, goal=None, tech=None):
    persona = _persona(vault, archetype)
    if tech is not None:
        persona = persona.model_copy(update={"tech_comfort": tech})  # never misses a matching link
    arch = vault.archetypes[archetype]
    goal = goal or arch.goals_on_site[0]
    steps: list[HandsStep] = []

    async def on_step(p, s):
        steps.append(s)

    async with PlaywrightBrowser() as browser:
        driver = await browser.driver(persona.device)
        try:
            session = await run_session(
                driver=driver, provider=MockProvider(), vault=vault, persona=persona, archetype=arch, url=url,
                goal=goal, max_steps=20, shots_dir=tmp_path, shot_prefix=persona.id, on_step=on_step,
            )
        finally:
            await driver.close()
    return persona, session, steps


async def test_mother_gives_up_looking_for_price(vault, tmp_path, site_url):
    persona, session, steps = await _session(vault, tmp_path, f"{site_url}/fitdesk-cluttered/", "mother")
    assert session.outcome == "gave_up", session.summary
    assert session.seconds >= persona.patience_seconds
    assert any(s.action == "scroll" for s in session.steps)
    assert len(steps) == len(session.steps)
    assert all((tmp_path / s.screenshot).is_file() for s in session.steps if s.screenshot)


async def test_corporate_worker_finds_calendar_sync(vault, tmp_path, site_url):
    _, session, _ = await _session(vault, tmp_path, f"{site_url}/fitdesk-cluttered/", "corporate-worker")
    assert session.outcome == "success", [s.model_dump() for s in session.steps]
    assert any(s.action == "click" and s.target_label == "Integrations" for s in session.steps)


async def test_run_goal_overrides_archetype_goal(vault, tmp_path, site_url):
    """A student sent to read the stories clicks Stories, not a pricing link."""
    _, session, _ = await _session(vault, tmp_path, f"{site_url}/fitdesk-cluttered/", "student", goal="read the stories from users", tech=1.0)
    assert session.goal == "read the stories from users"
    assert any(s.action == "click" and s.target_label == "Stories" for s in session.steps), [s.model_dump() for s in session.steps]


def test_hands_request_goal_precedence(vault):
    arch = vault.archetypes["student"]
    assert HandsRequest(url="http://x").goal_for(arch) == arch.goals_on_site[0]
    assert HandsRequest(url="http://x", goal="g").goal_for(arch) == "g"
    assert HandsRequest(url="http://x", goal="g", goals={"student": "s"}).goal_for(arch) == "s"


async def test_full_pipeline_with_hands(vault, settings, brief, site_url):
    store = Store(settings.db_path)
    runtime = SettingsStore(settings.data_dir / "settings.json", defaults_from(settings))
    pipe = Pipeline(settings, vault, store, EventBus(store), runtime)
    hands = HandsRequest(url=f"{site_url}/fitdesk-cluttered/", personas=3, max_steps=12, archetypes=["mother"])
    req = RunRequest(brief=brief, crowd_size=120, hands=hands)
    run_id = pipe.start(req)
    await pipe.execute(run_id, req)
    run = store.get_run(run_id)
    assert run["status"] == "finished", run["error"]
    types = [e.type for e in store.get_events(run_id)]
    assert types[0] == "run.started" and types[-1] == "run.finished"
    assert types.count("reaction") == 120 and types.count("hands.session") == 3
    sessions = store.get_sessions(run_id)
    assert {s.archetype_id for s in sessions} >= {"mother", "corporate-worker"}
    assert (settings.artifacts_dir / run_id / "report.json").is_file()
    store.close()


def test_api_run_and_event_stream(settings, brief):
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/health").json()["provider"] == "mock"
        assert len(client.get("/api/archetypes").json()) == 10
        bad = client.post("/api/runs", json={"brief": brief.model_dump(), "mix": {"pirate": 1}})
        assert bad.status_code == 422
        run_id = client.post("/api/runs", json={"brief": brief.model_dump(), "crowd_size": 60}).json()["run_id"]

        with client.stream("GET", f"/api/runs/{run_id}/events") as resp:
            assert resp.headers["content-type"].startswith("text/event-stream")
            events = [line[7:] for line in resp.iter_lines() if line.startswith("event: ")]
        assert events[0] == "run.started" and events[-1] == "run.finished"
        assert events.count("reaction") == 60

        run = client.get(f"/api/runs/{run_id}").json()
        assert run["status"] == "finished" and run["summary"]["best_segment"]
        rows = client.get(f"/api/runs/{run_id}/reactions", params={"segment": "mother"}).json()
        assert rows and all(r["persona"]["archetype_id"] == "mother" for r in rows)
        assert client.get(f"/api/runs/{run_id}/docs").json()["prd_md"].startswith("# Product Requirements")
        pid = rows[0]["persona"]["id"]
        answer = client.post(f"/api/runs/{run_id}/personas/{pid}/interview", json={"question": "Would you pay?"})
        assert answer.status_code == 200 and answer.json()["answer"]
        assert client.get(f"/api/runs/{run_id}/artifacts/../../crowdpod.sqlite3").status_code == 404
