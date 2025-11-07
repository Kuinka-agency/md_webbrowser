from __future__ import annotations

import pytest
import sys
import types

from fastapi.testclient import TestClient

from app import main as app_main

if "pyvips" not in sys.modules:
    sys.modules["pyvips"] = types.ModuleType("pyvips")


class StubJobManager:
    def __init__(self, *, deleted: int = 1, error: Exception | None = None) -> None:
        self.deleted = deleted
        self.error = error
        self.calls: list[tuple[str, int | None, str | None]] = []

    def delete_webhook(self, job_id: str, *, webhook_id: int | None = None, url: str | None = None) -> int:
        self.calls.append((job_id, webhook_id, url))
        if self.error:
            raise self.error
        return self.deleted


def get_client(monkeypatch, stub_manager: StubJobManager) -> TestClient:
    monkeypatch.setattr(app_main, "JOB_MANAGER", stub_manager)
    return TestClient(app_main.app)


def test_delete_webhook_success(monkeypatch):
    stub = StubJobManager(deleted=2)
    client = get_client(monkeypatch, stub)

    response = client.request(
        "DELETE",
        "/jobs/job-1/webhooks",
        json={"url": "https://example.com/hook"},
    )

    assert response.status_code == 200
    assert response.json() == {"job_id": "job-1", "deleted": 2}
    assert stub.calls == [("job-1", None, "https://example.com/hook")]


def test_delete_webhook_missing_identifier(monkeypatch):
    stub = StubJobManager()
    client = get_client(monkeypatch, stub)

    response = client.request("DELETE", "/jobs/job-1/webhooks", json={})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any("Provide id or url" in entry.get("msg", "") for entry in detail)


@pytest.mark.parametrize("error,expected_status", [(KeyError("missing"), 404), (ValueError("bad"), 400)])
def test_delete_webhook_errors(monkeypatch, error, expected_status):
    stub = StubJobManager(error=error)
    client = get_client(monkeypatch, stub)

    response = client.request(
        "DELETE",
        "/jobs/job-x/webhooks",
        json={"id": 1},
    )

    assert response.status_code == expected_status
