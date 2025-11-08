from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from typer.testing import CliRunner

from scripts import mdwb_cli

console = Console(record=True)
runner = CliRunner()


class StubClient:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses

    def get(self, path: str):  # noqa: ANN001
        resp = self.responses.get(path)
        if resp is None:
            raise KeyError(path)
        return resp

    def post(self, path: str, json=None):  # noqa: ANN001
        resp = self.responses.get(path)
        if resp is None:
            raise KeyError(path)
        return resp

    def close(self) -> None:
        return None


class StubResponse:
    def __init__(self, status_code: int, payload: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):  # noqa: ANN001
        if self._payload is not None:
            return self._payload
        return json.loads(self.text)

    def iter_lines(self):  # noqa: ANN001
        payload = self.text.splitlines()
        for line in payload:
            yield line

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.text or f"HTTP {self.status_code}")


@contextmanager
def stubbed_client(responses):
    client = StubClient(responses)
    yield client


def _fake_settings():
    return mdwb_cli.APISettings(base_url="http://localhost", api_key=None, warning_log_path=Path("ops/warnings.jsonl"))


@contextmanager
def _patched_client(monkeypatch, responses: dict[str, Any]):
    monkeypatch.setattr(mdwb_cli, "_client_ctx", lambda settings, http2=True: stubbed_client(responses))
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda base: _fake_settings())
    yield


def _log_panel(title: str, content: str) -> None:
    console.print(Panel(content, title=title))


def _log_table(title: str, rows: list[tuple[str, str]]) -> None:
    table = Table("Step", "Details", title=title)
    for step, detail in rows:
        table.add_row(step, detail)
    console.print(table)


def test_e2e_fetch_resume(monkeypatch, tmp_path: Path):
    manifest = {"id": "job123", "state": "DONE"}
    responses = {
        "/jobs/job123": StubResponse(200, payload=manifest),
        "/jobs/job123/stream": StubResponse(200, text="event:state\ndata:DONE\n\n"),
    }
    with _patched_client(monkeypatch, responses):
        _log_panel("Fetch Resume Inputs", Syntax("mdwb fetch --resume job123", "bash"))
        result = runner.invoke(mdwb_cli.cli, ["fetch", "https://example.com", "--resume", "--watch"])
        _log_panel("Fetch Resume Output", result.output)
        assert result.exit_code == 0


def test_e2e_agents_summary(monkeypatch, tmp_path: Path):
    lyrics_path = tmp_path / "log.jsonl"
    lyrics_path.write_text(json.dumps({"job_id": "demo"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda base: _fake_settings())
    monkeypatch.setattr(mdwb_cli.console, "print", console.print)
    result = runner.invoke(mdwb_cli.cli, ["agents", "summarize", "https://example.com", "--log-path", str(lyrics_path)])
    _log_panel("Agents Summarize Output", result.output)
    assert result.exit_code == 0


def test_e2e_warning_tail(monkeypatch, tmp_path: Path):
    log_path = tmp_path / "warnings.jsonl"
    log_path.write_text(json.dumps({"timestamp": "2025-11-08T08:00:00Z", "job_id": "run-1", "warnings": []}) + "\n", encoding="utf-8")
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda base: _fake_settings())
    result = runner.invoke(
        mdwb_cli.cli,
        ["warnings", "tail", "--count", "1", "--json", "--log-path", str(log_path)],
    )
    _log_table("Warnings Tail", [("Raw", result.output)])
    assert result.exit_code == 0
