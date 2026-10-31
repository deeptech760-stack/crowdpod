"""Claude as the brain, and the security rules around model settings and browsing."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from crowdpod.api import create_app
from crowdpod.models import HandsRequest

from .fake_llm import FakeLLM

BROWSER = {"show_windows": False, "slow_mo_ms": 0, "parallel": 1}


@pytest.fixture
def fake_llm():
    server = FakeLLM()
    yield server
    server.close()


def _claude(fake: FakeLLM, **extra):
    # base_url points the Anthropic client at the local fake; real use leaves it empty
    return {"provider": "anthropic", "base_url": fake.root, "model": "claude-opus-5-5",
            "concurrency": 2, "batch_size": 10, "effort": "low", **extra}


def test_run_driven_by_claude(settings, brief, fake_llm, site_url):
    with TestClient(create_app(settings)) as client:
        assert client.put("/api/settings", json={"brain": _claude(fake_llm, api_key="sk-ant-test-9876"), "browser": BROWSER}).status_code == 200
        assert client.post("/api/settings/test", json=_claude(fake_llm)).json()["ok"]
        assert client.post("/api/settings/models", json=_claude(fake_llm)).json()["models"] == ["claude-opus-5-5"]

        req = {"brief": brief.model_dump(), "crowd_size": 20,
               "hands": {"url": f"{site_url}/fitdesk-cluttered/", "personas": 1, "max_steps": 3}}
        run_id = client.post("/api/runs", json=req).json()["run_id"]
        with client.stream("GET", f"/api/runs/{run_id}/events") as resp:
            events = [line[7:] for line in resp.iter_lines() if line.startswith("event: ")]
        assert events[-1] == "run.finished" and "crowd.degraded" not in events
        assert client.get(f"/api/runs/{run_id}").json()["provider"] == "claude-opus-5-5 @ Anthropic API"
        rows = client.get(f"/api/runs/{run_id}/reactions").json()
        assert len(rows) == 20 and all(r["reaction"]["provider"] == "anthropic" for r in rows)
        assert client.get(f"/api/runs/{run_id}/docs").json()["prd_md"].startswith("# Doc from fake model")

    calls = [r for r in fake_llm.requests if r.get("path", "").startswith("/v1/messages")]
    # test call + research + digest + audience design + 2 crowd batches + 2 documents + 1 browser step
    assert len(calls) == 9
    research_call = next(r for r in calls if "market researcher" in r["body"].get("system", ""))
    assert research_call["body"]["tools"][0]["name"] == "web_search"
    assert {r["auth"] for r in calls} == {"sk-ant-test-9876"}
    assert all("server-side-fallback-2026-07-01" in (r["beta"] or "") for r in calls)
    assert all(r["body"]["fallbacks"] == "default" and r["body"]["output_config"]["effort"] == "low" for r in calls)
    # digest, audience, crowd and browser calls ask for schema-checked JSON
    assert sum("format" in r["body"]["output_config"] for r in calls) == 6


def test_claude_needs_a_key(settings):
    with TestClient(create_app(settings)) as client:
        r = client.put("/api/settings", json={"brain": {"provider": "anthropic", "model": "claude-opus-5-5"}, "browser": BROWSER})
        assert r.status_code == 422 and "API key" in r.text


def test_saved_key_never_goes_to_another_service(settings, fake_llm):
    with TestClient(create_app(settings)) as client:
        openai_like = {"provider": "openai", "base_url": fake_llm.base_url, "model": "fake-small",
                       "concurrency": 2, "batch_size": 10, "api_key": "openrouter-key-1111"}
        assert client.put("/api/settings", json={"brain": openai_like, "browser": BROWSER}).status_code == 200
        # switching to Claude without typing a key must not reuse the OpenRouter key
        r = client.put("/api/settings", json={"brain": _claude(fake_llm), "browser": BROWSER})
        assert r.status_code == 422
        # pointing the same provider at a different address doesn't reuse it either
        moved = {**openai_like, "api_key": None, "base_url": "http://127.0.0.1:9/v1"}
        assert client.put("/api/settings", json={"brain": moved, "browser": BROWSER}).json()["brain"]["has_key"] is False
    assert not any(r["auth"] in ("openrouter-key-1111", "Bearer openrouter-key-1111") and r.get("path") for r in fake_llm.requests)


def test_key_is_redacted_from_errors(settings):
    with TestClient(create_app(settings)) as client:
        # an unreachable endpoint; whatever the error says, the key must not come back
        body = {"provider": "openai", "base_url": "http://127.0.0.1:9/v1", "model": "m", "api_key": "secret-key-5555"}
        detail = client.post("/api/settings/test", json=body).json()["detail"]
        assert "secret-key-5555" not in detail
        assert "secret-key-5555" not in client.get("/api/settings").text


def test_settings_only_from_this_machine(settings):
    app = create_app(settings)
    with TestClient(app, client=("203.0.113.7", 50000)) as remote:
        assert remote.get("/api/health").status_code == 200  # reading results is fine
        assert remote.put("/api/settings", json={"brain": {"provider": "mock"}, "browser": BROWSER}).status_code == 403
        assert remote.post("/api/settings/test", json={"provider": "mock"}).status_code == 403
        assert remote.post("/api/settings/models", json={"provider": "mock"}).status_code == 403


def test_unknown_host_header_is_rejected(settings):
    """A web page that rebinds its own domain to 127.0.0.1 still sends its own Host header."""
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 400
        assert client.get("/api/health", headers={"host": "localhost:8000"}).status_code == 200


@pytest.mark.parametrize("url", ["file:///C:/Windows/win.ini", "javascript:alert(1)", "ftp://x.example", "example.com"])
def test_browser_agents_only_visit_web_pages(url):
    with pytest.raises(ValidationError):
        HandsRequest(url=url)
