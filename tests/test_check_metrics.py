from __future__ import annotations

import json

from typer.testing import CliRunner

from scripts import check_metrics

runner = CliRunner()


class StubConfig:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    def __call__(self, key: str, cast=None, default=None):  # noqa: ANN001
        value = self.values.get(key, default)
        if cast and value is not None:
            return cast(value)
        return value


def test_run_check_probes_primary_and_exporter(monkeypatch):
    called: list[str] = []

    def fake_probe(url: str, timeout: float) -> None:  # noqa: ANN001
        called.append(url)

    monkeypatch.setattr(check_metrics, "_probe", fake_probe)
    monkeypatch.setattr(check_metrics, "_load_config", lambda: StubConfig({"API_BASE_URL": "http://api", "PROMETHEUS_PORT": 9100}))

    result = runner.invoke(check_metrics.cli, ["--timeout", "1.0"])

    assert result.exit_code == 0
    assert called == ["http://api/metrics", "http://localhost:9100/metrics"]


def test_run_check_json_output(monkeypatch):
    monkeypatch.setattr(check_metrics, "_probe", lambda url, timeout: None)
    monkeypatch.setattr(check_metrics, "_load_config", lambda: StubConfig({"API_BASE_URL": "http://api", "PROMETHEUS_PORT": 9200}))

    result = runner.invoke(check_metrics.cli, ["--json", "--no-include-exporter"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["ok_count"] == 1
    assert payload["failed_count"] == 0
    assert "generated_at" in payload
    assert payload["targets"] == [{"url": "http://api/metrics", "ok": True}]


def test_exporter_url_override(monkeypatch):
    called: list[str] = []

    def fake_probe(url: str, timeout: float) -> None:  # noqa: ANN001
        called.append(url)

    monkeypatch.setattr(check_metrics, "_probe", fake_probe)
    monkeypatch.setattr(check_metrics, "_load_config", lambda: StubConfig({"API_BASE_URL": "http://api", "PROMETHEUS_PORT": 9100}))

    result = runner.invoke(
        check_metrics.cli,
        [
            "--exporter-url",
            "https://prom.internal/metrics",
        ],
    )

    assert result.exit_code == 0
    assert called == ["http://api/metrics", "https://prom.internal/metrics"]


def test_run_check_reports_failures(monkeypatch):
    def fake_probe(url: str, timeout: float) -> None:  # noqa: ANN001
        raise RuntimeError("boom")

    monkeypatch.setattr(check_metrics, "_probe", fake_probe)
    monkeypatch.setattr(check_metrics, "_load_config", lambda: StubConfig({"API_BASE_URL": "http://api", "PROMETHEUS_PORT": 9000}))

    result = runner.invoke(check_metrics.cli, ["--no-include-exporter"])

    assert result.exit_code == 1
    assert "[FAIL] http://api/metrics" in result.output


def test_run_check_json_reports_failures(monkeypatch):
    def fake_probe(url: str, timeout: float) -> None:  # noqa: ANN001
        raise RuntimeError("boom")

    monkeypatch.setattr(check_metrics, "_probe", fake_probe)
    monkeypatch.setattr(check_metrics, "_load_config", lambda: StubConfig({"API_BASE_URL": "http://api", "PROMETHEUS_PORT": 9000}))

    result = runner.invoke(check_metrics.cli, ["--json", "--no-include-exporter"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "error"
    assert payload["failed_count"] == 1
    assert payload["targets"][0]["ok"] is False
