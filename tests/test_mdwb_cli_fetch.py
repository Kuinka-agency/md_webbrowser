from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any

from typer.testing import CliRunner
import zstandard as zstd

from scripts import mdwb_cli

runner = CliRunner()


class DummyResponse:
    def __init__(self, status_code: int, payload=None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):  # noqa: ANN001
        return self._payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.text or f"status {self.status_code}")


def _fake_settings():
    return mdwb_cli.APISettings(
        base_url="http://localhost",
        api_key=None,
        warning_log_path=Path("ops/warnings.jsonl"),
    )


def _write_resume_state(root: Path, group_hash: str, entries: list[str]) -> None:
    index_path = root / "work_index_list.csv.zst"
    done_dir = root / "done_flags"
    done_dir.mkdir(parents=True, exist_ok=True)
    (done_dir / f"done_{group_hash}.flag").write_text("", encoding="utf-8")
    csv_line = ",".join([group_hash, *entries]) + "\n"
    compressed = zstd.ZstdCompressor().compress(csv_line.encode("utf-8"))
    index_path.write_bytes(compressed)


def _write_resume_index(root: Path, rows: list[tuple[str, list[str]]]) -> None:
    index_path = root / "work_index_list.csv.zst"
    payload = "".join(",".join([group_hash, *entries]) + "\n" for group_hash, entries in rows)
    compressed = zstd.ZstdCompressor().compress(payload.encode("utf-8"))
    index_path.write_bytes(compressed)


def test_fetch_with_webhook_urls(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class FakeClient:
        def __init__(self) -> None:
            self.calls = calls

        def post(self, url: str, json=None):  # noqa: ANN001
            payload = json or {}
            self.calls.append((url, payload))
            if url == "/jobs":
                return DummyResponse(200, {"id": "job-123"})
            return DummyResponse(202)

        def close(self) -> None:  # pragma: no cover - simple stub
            return None

    monkeypatch.setattr(mdwb_cli, "_client", lambda settings, http2=True, **_: FakeClient())
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda base: _fake_settings())

    result = runner.invoke(
        mdwb_cli.cli,
        [
            "fetch",
            "https://example.com",
            "--webhook-url",
            "https://foo/hook",
            "--webhook-url",
            "https://bar/hook",
        ],
    )

    assert result.exit_code == 0
    assert calls[0][0] == "/jobs"
    assert calls[1][0] == "/jobs/job-123/webhooks"
    assert calls[2][0] == "/jobs/job-123/webhooks"


def test_fetch_handles_webhook_failure(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class FakeClient:
        def post(self, url: str, json=None):  # noqa: ANN001
            payload = json or {}
            calls.append((url, payload))
            if url == "/jobs":
                return DummyResponse(200, {"id": "job-123"})
            return DummyResponse(500, text="boom")

        def close(self) -> None:  # pragma: no cover - simple stub
            return None

    monkeypatch.setattr(mdwb_cli, "_client", lambda settings, http2=True, **_: FakeClient())
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda base: _fake_settings())

    result = runner.invoke(
        mdwb_cli.cli,
        [
            "fetch",
            "https://example.com",
            "--webhook-url",
            "https://foo/hook",
            "--webhook-event",
            "DONE",
            "--webhook-event",
            "FAILED",
        ],
    )

    assert result.exit_code == 0
    assert "Failed to register webhook" in result.output
    assert calls[-1][1] == {"url": "https://foo/hook", "events": ["DONE", "FAILED"]}


def test_fetch_cache_flag(monkeypatch):
    calls: list[dict] = []

    class FakeClient:
        def post(self, url: str, json=None):  # noqa: ANN001
            if url == "/jobs":
                calls.append(json or {})
                return DummyResponse(200, {"id": "job-555"})
            return DummyResponse(202)

        def close(self) -> None:  # pragma: no cover - stub
            return None

    monkeypatch.setattr(mdwb_cli, "_client", lambda settings, http2=True, **_: FakeClient())
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda base: _fake_settings())

    result = runner.invoke(
        mdwb_cli.cli,
        [
            "fetch",
            "https://cache.example",
            "--no-cache",
        ],
    )

    assert result.exit_code == 0
    assert calls and calls[0]["reuse_cache"] is False


def test_fetch_resume_skips_completed_url(monkeypatch, tmp_path):
    _write_resume_state(tmp_path, mdwb_cli._resume_hash("https://example.com"), ["https://example.com"])
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda base: _fake_settings())

    @contextmanager
    def _fail_client(*_args, **_kwargs):
        raise AssertionError("client should not run when resume skips")
        yield

    monkeypatch.setattr(mdwb_cli, "_client_ctx", _fail_client)

    result = runner.invoke(
        mdwb_cli.cli,
        [
            "fetch",
            "https://example.com",
            "--resume",
            "--resume-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "already marked complete" in result.output


def test_fetch_resume_submits_new_url(monkeypatch, tmp_path):
    _write_resume_state(tmp_path, mdwb_cli._resume_hash("https://done.example"), ["https://done.example"])
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda base: _fake_settings())

    calls: list[tuple[str, dict]] = []

    class FakeClient:
        def post(self, url: str, json=None):  # noqa: ANN001
            payload = json or {}
            calls.append((url, payload))
            if url == "/jobs":
                return DummyResponse(200, {"id": "job-789"})
            return DummyResponse(202)

        def close(self) -> None:  # pragma: no cover - simple stub
            return None

    @contextmanager
    def _client_ctx(*_args, **_kwargs):
        yield FakeClient()

    monkeypatch.setattr(mdwb_cli, "_client_ctx", _client_ctx)
    def _fake_watch(*_args, **kwargs):
        cb = kwargs.get("on_terminal")
        if cb:
            cb("DONE", {"state": "DONE"})

    monkeypatch.setattr(mdwb_cli, "_watch_events_with_fallback", _fake_watch)

    result = runner.invoke(
        mdwb_cli.cli,
        [
            "fetch",
            "https://new.example",
            "--resume",
            "--resume-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert calls and calls[0][0] == "/jobs"


def test_fetch_resume_marks_completion(monkeypatch, tmp_path):
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda base: _fake_settings())

    class FakeClient:
        def post(self, url: str, json=None):  # noqa: ANN001
            if url == "/jobs":
                return DummyResponse(200, {"id": "job-999"})
            return DummyResponse(202)

        def close(self) -> None:  # pragma: no cover - simple stub
            return None

    @contextmanager
    def _client_ctx(*_args, **_kwargs):
        yield FakeClient()

    def _fake_watch(*_args, **kwargs):
        cb = kwargs.get("on_terminal")
        if cb:
            cb("DONE", {"state": "DONE"})

    monkeypatch.setattr(mdwb_cli, "_client_ctx", _client_ctx)
    monkeypatch.setattr(mdwb_cli, "_watch_events_with_fallback", _fake_watch)

    result = runner.invoke(
        mdwb_cli.cli,
        [
            "fetch",
            "https://resume.example",
            "--resume",
            "--resume-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    group_hash = mdwb_cli._resume_hash("https://resume.example")
    flag = tmp_path / "done_flags" / f"done_{group_hash}.flag"
    assert flag.exists()


def test_fetch_requires_watch_when_on_event(monkeypatch):
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda base: _fake_settings())

    result = runner.invoke(
        mdwb_cli.cli,
        [
            "fetch",
            "https://example.com",
            "--on",
            "state:DONE=echo hi",
        ],
    )

    assert result.exit_code != 0
    assert "--on requires --watch" in result.output


def test_fetch_watch_passes_event_hooks(monkeypatch):
    settings = _fake_settings()
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda base: settings)

    class FakeClient:
        def __init__(self) -> None:
            self.closed = False
            self.calls: list[str] = []

        def post(self, url: str, json=None):  # noqa: ANN001
            self.calls.append(url)
            return DummyResponse(200, {"id": "job-abc"})

        def close(self) -> None:
            self.closed = True

    shared_client = FakeClient()
    monkeypatch.setattr(mdwb_cli, "_client", lambda *_, **__: shared_client)
    monkeypatch.setattr(mdwb_cli, "_register_webhooks_for_job", lambda *_, **__: None)

    captured: dict[str, Any] = {}

    def fake_watch(job_id, settings, cursor, follow, interval, raw, hooks, on_terminal=None, progress_meter=None, client=None):  # noqa: ANN001,E501
        captured.update(
            {
                "job_id": job_id,
                "hooks": hooks,
                "client": client,
            }
        )

    monkeypatch.setattr(mdwb_cli, "_watch_events_with_fallback", fake_watch)

    result = runner.invoke(
        mdwb_cli.cli,
        [
            "fetch",
            "https://example.com",
            "--watch",
            "--reuse-session",
            "--on",
            "state:DONE=echo finish",
        ],
    )

    assert result.exit_code == 0
    assert captured["job_id"] == "job-abc"
    assert captured["hooks"] == {"state:DONE": ["echo finish"]}
    assert captured["client"] is shared_client
    assert shared_client.closed


def test_fetch_reuse_session_reuses_http_client(monkeypatch):
    settings = _fake_settings()
    monkeypatch.setattr(mdwb_cli, "_resolve_settings", lambda base: settings)

    class FakeClient:
        def __init__(self) -> None:
            self.closed = False
            self.calls: list[str] = []

        def post(self, url: str, json=None):  # noqa: ANN001
            self.calls.append(url)
            return DummyResponse(200, {"id": "job-123"})

        def close(self) -> None:
            self.closed = True

    shared_client = FakeClient()
    monkeypatch.setattr(mdwb_cli, "_client", lambda *_, **__: shared_client)
    monkeypatch.setattr(mdwb_cli, "_register_webhooks_for_job", lambda *_, **__: None)

    watch_calls: dict[str, object] = {}

    def fake_watch(*, client=None, **_):  # noqa: ANN001
        watch_calls["client"] = client

    monkeypatch.setattr(mdwb_cli, "_watch_events_with_fallback", lambda *args, **kwargs: fake_watch(**kwargs))

    result = runner.invoke(
        mdwb_cli.cli,
        ["fetch", "https://reuse.example", "--watch", "--reuse-session"],
    )

    assert result.exit_code == 0
    assert shared_client.closed
    assert watch_calls["client"] is shared_client


def test_resume_manager_list_entries_filters_completed(tmp_path):
    done_url = "https://done.example/a"
    pending_url = "https://pending.example/b"
    done_hash = mdwb_cli._resume_hash(done_url)
    pending_hash = mdwb_cli._resume_hash(pending_url)
    _write_resume_index(
        tmp_path,
        [
            (done_hash, [done_url]),
            (pending_hash, [pending_url]),
        ],
    )
    done_dir = tmp_path / "done_flags"
    done_dir.mkdir(parents=True, exist_ok=True)
    (done_dir / f"done_{done_hash}.flag").write_text("", encoding="utf-8")

    manager = mdwb_cli.ResumeManager(tmp_path)
    entries = manager.list_entries()

    assert entries == [done_url]
