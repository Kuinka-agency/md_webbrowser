from __future__ import annotations

from pathlib import Path

import typer

from scripts import mdwb_cli

API_SETTINGS = mdwb_cli.APISettings(
    base_url="http://localhost",
    api_key=None,
    warning_log_path=Path("ops/warnings.jsonl"),
)


class StubResponse:
    def __init__(self, *, status_code: int = 200, payload=None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or []
        self.text = text

    def json(self):  # noqa: D401
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class StubClient:
    def __init__(self) -> None:
        self.called = []
        self.deleted = []

    def get(self, path):  # noqa: ANN001
        self.called.append(path)
        return StubResponse(payload=[{"url": "https://example.com", "events": ["DONE"], "created_at": "2025"}])

    def delete(self, path, json=None):  # noqa: ANN001
        self.deleted.append((path, json))
        return StubResponse(payload={"deleted": 1})

    def request(self, method: str, path: str, json=None):  # noqa: ANN001
        if method == "DELETE":
            self.deleted.append((path, json))
            return StubResponse(payload={"deleted": 1})
        raise AssertionError(f"Unexpected method {method}")


def test_jobs_webhooks_list_prints_table(monkeypatch):
    stub_client = StubClient()
    monkeypatch.setattr(mdwb_cli, "_client", lambda settings: stub_client)
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda api_base: API_SETTINGS)

    with mdwb_cli.console.capture() as capture:
        mdwb_cli.jobs_webhooks_list("job-1")

    assert stub_client.called == ["/jobs/job-1/webhooks"]
    output = capture.get()
    assert "https://example.com" in output


def test_jobs_webhooks_delete_requires_identifier(monkeypatch):
    stub_client = StubClient()
    monkeypatch.setattr(mdwb_cli, "_client", lambda settings: stub_client)
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda api_base: API_SETTINGS)
    try:
        mdwb_cli.jobs_webhooks_delete("job-1")
    except typer.BadParameter:
        pass
    else:
        raise AssertionError("Expected typer.BadParameter when no id/url provided")


def test_jobs_webhooks_delete_calls_api(monkeypatch):
    stub_client = StubClient()
    monkeypatch.setattr(mdwb_cli, "_client", lambda settings: stub_client)
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda api_base: API_SETTINGS)

    with mdwb_cli.console.capture():
        mdwb_cli.jobs_webhooks_delete("job-1", url="https://example.com")

    assert stub_client.deleted == [
        ("/jobs/job-1/webhooks", {"url": "https://example.com"})
    ]
