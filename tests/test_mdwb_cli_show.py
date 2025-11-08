from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from scripts import mdwb_cli

runner = CliRunner()


class StubResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self):  # noqa: ANN001
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class StubClient:
    def __init__(self, responses: dict[str, StubResponse]) -> None:
        self.responses = responses

    def get(self, path: str):  # noqa: ANN001
        response = self.responses.get(path)
        if response is None:
            raise KeyError(f"unexpected path {path}")
        return response

    def close(self) -> None:  # pragma: no cover - simple stub
        return None


def _fake_settings():
    return mdwb_cli.APISettings(base_url="http://localhost", api_key=None, warning_log_path=Path("ops/warnings.jsonl"))


def test_jobs_show_prints_sweep_and_validation_summary(monkeypatch):
    manifest = {
        "warnings": [],
        "blocklist_hits": {},
        "sweep_stats": {
            "sweep_count": 5,
            "shrink_events": 1,
            "retry_attempts": 1,
            "overlap_pairs": 4,
            "overlap_match_ratio": 0.82,
        },
        "overlap_match_ratio": 0.82,
        "validation_failures": ["tile checksum mismatch"],
    }
    snapshot = {"id": "job123", "state": "DONE", "url": "https://example.com", "progress": {"done": 5, "total": 5}, "manifest": manifest}
    responses = {"/jobs/job123": StubResponse(snapshot)}

    def fake_client_ctx(settings, http2=True, timeout=None):  # noqa: ANN001, ARG001
        @contextmanager
        def _ctx():
            yield StubClient(responses)

        return _ctx()

    monkeypatch.setattr(mdwb_cli, "_client_ctx", fake_client_ctx)
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda base: _fake_settings())

    result = runner.invoke(mdwb_cli.cli, ["show", "job123"])

    assert result.exit_code == 0
    assert "sweep" in result.output.lower()
    assert "ratio=0.82" in result.output
    assert "validation" in result.output.lower()
    assert "checksum mismatch" in result.output
