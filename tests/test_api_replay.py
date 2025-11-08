from __future__ import annotations

import types
import sys

from fastapi.testclient import TestClient

from app import main as app_main
from app.jobs import JobState

if "pyvips" not in sys.modules:
    sys.modules["pyvips"] = types.ModuleType("pyvips")


class StubReplayManager:
    def __init__(self, *, snapshot: dict, error: Exception | None = None) -> None:
        self.snapshot = snapshot
        self.error = error
        self.calls: list[dict] = []

    async def replay_job(self, manifest: dict) -> dict:
        self.calls.append(manifest)
        if self.error:
            raise self.error
        return self.snapshot


def make_snapshot(job_id: str, url: str) -> dict:
    return {
        "id": job_id,
        "url": url,
        "state": JobState.BROWSER_STARTING,
        "progress": {"done": 0, "total": 0},
        "manifest_path": "",
        "manifest": None,
    }


def get_client(monkeypatch, stub_manager: StubReplayManager) -> TestClient:
    monkeypatch.setattr(app_main, "JOB_MANAGER", stub_manager)
    return TestClient(app_main.app)


def test_replay_success(monkeypatch):
    manifest = {"url": "https://example.com/article", "job_id": "old-job"}
    stub = StubReplayManager(snapshot=make_snapshot("new-job", manifest["url"]))
    client = get_client(monkeypatch, stub)

    response = client.post("/replay", json={"manifest": manifest})

    assert response.status_code == 202
    payload = response.json()
    assert payload["id"] == "new-job"
    assert stub.calls == [manifest]


def test_replay_missing_url(monkeypatch):
    stub = StubReplayManager(snapshot=make_snapshot("job-x", "https://irrelevant"))
    client = get_client(monkeypatch, stub)

    response = client.post("/replay", json={"manifest": {"job_id": "missing"}})

    assert response.status_code == 422


def test_replay_job_manager_error(monkeypatch):
    manifest = {"url": "https://example.com"}
    stub = StubReplayManager(snapshot=make_snapshot("job-y", manifest["url"]), error=ValueError("boom"))
    client = get_client(monkeypatch, stub)

    response = client.post("/replay", json={"manifest": manifest})

    assert response.status_code == 400
