"""People the user describes become full personas and their own segments of the crowd."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from crowdpod.api import create_app
from crowdpod.describe import persona_from_description
from crowdpod.models import IdeaBrief

PEOPLE = [
    "A final-year engineering student in Pune, broke, only uses free apps, impatient",
    "Retired schoolteacher in her 60s from Jaipur, not tech-savvy, careful with money, uses her grandson's old phone",
    "Busy 34 year old product manager in Bengaluru, iPhone and MacBook, spends ₹3000 a month on subscriptions",
]


def test_descriptions_become_constrained_personas(vault, brief):
    student, teacher, pm = (persona_from_description(d, brief, vault, i) for i, d in enumerate(PEOPLE))
    assert student.city == "Pune" and student.age == (18, 24)
    assert student.price_sensitivity[0] >= 0.8 and student.patience_seconds[1] <= 25  # "impatient", not "patient"
    assert teacher.age == (60, 69) and teacher.tech_comfort[1] <= 0.35  # "not tech-savvy" wins over "tech-savvy"
    assert teacher.devices == ["budget-android"] and teacher.label == "Retired schoolteacher"
    assert pm.city == "Bengaluru" and pm.age == (32, 36) and set(pm.devices) == {"iphone", "laptop"}
    assert 2000 <= pm.budget_month[0] <= 3000 <= pm.budget_month[1]
    assert "Corporate worker" in pm.evidence[1]
    for p in (student, teacher, pm):
        assert p.evidence[0].startswith("Described by the user:") and p.moods and p.objections


def test_described_people_join_the_crowd(settings):
    with TestClient(create_app(settings)) as client:
        run = client.post("/api/runs", json={
            "brief": {"name": "Tiffin Club", "pitch": "Home-cooked lunch subscriptions for office workers.", "price": 2500},
            "crowd_size": 120, "audience": "builtin", "described": PEOPLE,
        }).json()["run_id"]
        for _ in range(100):
            if client.get(f"/api/runs/{run}").json()["status"] in ("finished", "failed"):
                break
            time.sleep(0.1)
        info = client.get(f"/api/runs/{run}").json()
        assert info["status"] == "finished", info["error"]
        personas = client.get(f"/api/runs/{run}/audience").json()["personas"]
        assert [p["id"][:4] for p in personas] == ["you-"] * 3
        segments = {s["archetype_id"]: s["count"] for s in info["summary"]["segments"]}
        for p in personas:  # each described person is a real segment of the crowd
            assert segments.get(p["id"], 0) >= 3, (p["id"], segments)


def test_description_limits(settings):
    with TestClient(create_app(settings)) as client:
        base = {"brief": {"name": "x", "pitch": "a perfectly normal pitch"}, "crowd_size": 10, "audience": "builtin"}
        assert client.post("/api/runs", json={**base, "described": ["x" * 401]}).status_code == 422
        assert client.post("/api/runs", json={**base, "described": ["a student"] * 6}).status_code == 422
