"""The 'bring your own model' path, end to end, against a local fake OpenAI-compatible server."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from crowdpod.api import create_app

from .fake_llm import FakeLLM


@pytest.fixture
def fake_llm():
    server = FakeLLM()
    yield server
    server.close()


def _brain(fake: FakeLLM, **extra):
    return {"provider": "openai", "base_url": fake.base_url, "model": "fake-small", "concurrency": 2, "batch_size": 10, **extra}


BROWSER = {"show_windows": False, "slow_mo_ms": 0, "parallel": 1}


def test_settings_keep_the_key_server_side(settings, fake_llm):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/settings").json()["brain"]["provider"] == "mock"
        saved = client.put("/api/settings", json={"brain": _brain(fake_llm, api_key="test-key-1234"), "browser": BROWSER})
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert "api_key" not in body["brain"] and body["brain"]["has_key"] and body["brain"]["key_hint"] == "…1234"
        # saving again without a key keeps the stored one
        again = client.put("/api/settings", json={"brain": _brain(fake_llm), "browser": BROWSER}).json()
        assert again["brain"]["has_key"]
        on_disk = json.loads((settings.data_dir / "settings.json").read_text(encoding="utf-8"))
        assert on_disk["brain"]["api_key"] == "test-key-1234"
        assert client.get("/api/health").json()["provider"].startswith("fake-small @ 127.0.0.1:")
        # a custom model without a URL is refused
        bad = client.put("/api/settings", json={"brain": {"provider": "openai", "model": "x"}, "browser": BROWSER})
        assert bad.status_code == 422
        bad_url = client.put("/api/settings", json={"brain": _brain(fake_llm, base_url="ftp://x"), "browser": BROWSER})
        assert bad_url.status_code == 422


def test_connection_test_and_model_list(settings, fake_llm):
    with TestClient(create_app(settings)) as client:
        ok = client.post("/api/settings/test", json=_brain(fake_llm, api_key="k")).json()
        assert ok["ok"], ok
        assert client.post("/api/settings/models", json=_brain(fake_llm)).json()["models"] == ["fake-small"]
        down = client.post("/api/settings/test", json=_brain(fake_llm, base_url="http://127.0.0.1:9/v1")).json()
        assert not down["ok"] and down["detail"]


def test_run_driven_by_custom_model(settings, brief, fake_llm, site_url):
    with TestClient(create_app(settings)) as client:
        client.put("/api/settings", json={"brain": _brain(fake_llm, api_key="test-key-1234"), "browser": BROWSER})
        req = {"brief": brief.model_dump(), "crowd_size": 30,
               "hands": {"url": f"{site_url}/fitdesk-cluttered/", "personas": 2, "max_steps": 5}}
        run_id = client.post("/api/runs", json=req).json()["run_id"]
        with client.stream("GET", f"/api/runs/{run_id}/events") as resp:
            events = [line[7:] for line in resp.iter_lines() if line.startswith("event: ")]
        assert events[-1] == "run.finished", events[-5:]
        assert "crowd.degraded" not in events

        run = client.get(f"/api/runs/{run_id}").json()
        assert run["provider"].startswith("fake-small @")
        rows = client.get(f"/api/runs/{run_id}/reactions").json()
        assert len(rows) == 30 and all(r["reaction"]["provider"] == "openai" for r in rows)
        assert rows[0]["reaction"]["quote"].startswith("Fake quote")
        assert client.get(f"/api/runs/{run_id}/docs").json()["brd_md"].startswith("# Doc from fake model")
        sessions = client.get(f"/api/runs/{run_id}/hands").json()
        assert len(sessions) == 2 and all(s["outcome"] == "gave_up" for s in sessions)
        assert sessions[0]["steps"][0]["thought"] == "Nothing here for me."
        pid = rows[0]["persona"]["id"]
        assert client.post(f"/api/runs/{run_id}/personas/{pid}/interview", json={"question": "Why?"}).json()["answer"] == "Fake answer"

    # 3 crowd batches + 2 docs + 2 hands steps + 1 interview, all authenticated with the user's key
    assert len(fake_llm.requests) == 8
    assert {r["auth"] for r in fake_llm.requests} == {"Bearer test-key-1234"}
    assert all(r["body"]["model"] == "fake-small" for r in fake_llm.requests)
