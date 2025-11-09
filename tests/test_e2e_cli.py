from __future__ import annotations

import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from rich.console import Console
from typer.testing import CliRunner

from scripts import mdwb_cli
from scripts.agents import generate_todos, summarize_article
from scripts.agents import shared as agent_shared
from tests.rich_flowlogger import FlowLogger, create_console

runner = CliRunner()
RICH_TEMPLATE_HASH = "rich-e2e-cli-v1"
RICH_E2E_ARTIFACT_DIR = os.environ.get("RICH_E2E_ARTIFACT_DIR")


class DummyResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.text or f"status {self.status_code}")


def _export_transcripts(console: Console, artifact_root: Path, stem: str = "rich_e2e_cli") -> tuple[Path, Path]:
    artifact_root.mkdir(parents=True, exist_ok=True)
    log_path = artifact_root / f"{stem}.log"
    html_path = artifact_root / f"{stem}.html"
    log_path.write_text(console.export_text(clear=False), encoding="utf-8")
    html_path.write_text(console.export_html(clear=False), encoding="utf-8")
    if RICH_E2E_ARTIFACT_DIR:
        target_dir = Path(RICH_E2E_ARTIFACT_DIR)
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(log_path, target_dir / log_path.name)
        shutil.copy2(html_path, target_dir / html_path.name)
    return log_path, html_path


def _setup_console(monkeypatch, targets: Iterable[object]) -> Console:
    console = create_console()
    for target in targets:
        monkeypatch.setattr(target, "console", console)
    return console


def _resume_hash(identifier: str) -> str:
    return mdwb_cli._resume_hash(identifier)  # type: ignore[attr-defined]


def _capture_result(markdown: str) -> agent_shared.CaptureResult:
    return agent_shared.CaptureResult(job_id="demo-job", snapshot={"state": "DONE"}, markdown=markdown)


def test_e2e_fetch_resume_with_webhooks_rich_logging(monkeypatch, tmp_path: Path) -> None:
    url = "https://rich.example/article"
    resume_root = tmp_path / "resume"
    done_dir = resume_root / "done_flags"
    done_dir.mkdir(parents=True)
    (done_dir / f"done_{_resume_hash('https://other.example')}.flag").write_text("", encoding="utf-8")

    console = _setup_console(monkeypatch, [mdwb_cli])
    logger = FlowLogger(console, "mdwb fetch --resume --webhook")
    logger.banner("Resume + webhook run")
    logger.step(
        "Seed workspace",
        description="Prepare resume workspace so the CLI can log resume stats before submission.",
        inputs={
            "url": (url, "test"),
            "resume_root": (resume_root, "tmp_path"),
        },
        outputs={"done_dir": (done_dir, "resume state")},
        command=f"mkdir -p {done_dir}",
    )

    call_log: list[dict[str, Any]] = []

    class FakeClient:
        def post(self, path: str, json=None):  # noqa: ANN001
            payload = json or {}
            call_log.append({"path": path, "payload": payload})
            if path == "/jobs":
                return DummyResponse(200, {"id": "job-rich", "manifest_path": "/jobs/job-rich/manifest.json"})
            if path == "/jobs/job-rich/webhooks":
                return DummyResponse(200, {"status": "ok"})
            raise AssertionError(f"Unexpected path {path}")

        def close(self) -> None:  # pragma: no cover - simple stub
            return None

    monkeypatch.setattr(mdwb_cli, "_client", lambda settings, http2=True, **_: FakeClient())
    monkeypatch.setattr(
        mdwb_cli,
        "_resolve_settings",
        lambda api_base: mdwb_cli.APISettings("http://api", None, Path("ops/warnings.jsonl")),
    )

    watch_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        mdwb_cli,
        "_watch_events_with_fallback",
        lambda *args, **kwargs: watch_calls.append({"args": args, "kwargs": kwargs}),
    )

    function_calls: list[str] = []
    original_status = mdwb_cli.ResumeManager.status
    original_is_complete = mdwb_cli.ResumeManager.is_complete

    def tracking_status(self: mdwb_cli.ResumeManager) -> tuple[int, int | None]:
        function_calls.append("ResumeManager.status")
        return original_status(self)

    def tracking_is_complete(self: mdwb_cli.ResumeManager, entry: str) -> bool:
        function_calls.append("ResumeManager.is_complete")
        return original_is_complete(self, entry)

    monkeypatch.setattr(mdwb_cli.ResumeManager, "status", tracking_status)
    monkeypatch.setattr(mdwb_cli.ResumeManager, "is_complete", tracking_is_complete)

    command = (
        f"mdwb fetch {url} --resume --resume-root {resume_root} --webhook-url https://hooks/a "
        "--webhook-url https://hooks/b --watch"
    )
    logger.step(
        "Submit job",
        description="Invoke Typer command with resume + webhook flags to trigger HTTP + watcher flows.",
        inputs={
            "resume": (True, "cli flag"),
            "watch": (True, "resume auto-on"),
            "webhook_url": (2, "cli"),
        },
        functions=["ResumeManager.status", "ResumeManager.is_complete"],
        command=command,
    )

    result = runner.invoke(
        mdwb_cli.cli,
        [
            "fetch",
            url,
            "--resume",
            "--resume-root",
            str(resume_root),
            "--webhook-url",
            "https://hooks/a",
            "--webhook-url",
            "https://hooks/b",
            "--watch",
        ],
    )

    assert result.exit_code == 0
    webhook_calls = [entry for entry in call_log if entry["path"].endswith("/webhooks")]
    assert len(webhook_calls) == 2
    assert watch_calls, "watch events should run when --watch is enabled"

    logger.step(
        "Post-submit",
        description="Summarize HTTP calls and watcher activity to feed Rich tables.",
        functions=function_calls + ["_watch_events_with_fallback"],
        outputs={
            "job_id": ("job-rich", "FakeClient"),
            "manifest_path": ("/jobs/job-rich/manifest.json", "FakeClient"),
            "webhook_calls": (len(webhook_calls), "FakeClient"),
            "watch_calls": (len(watch_calls), "mdwb_cli"),
        },
        syntax_blocks=[("text", result.output)],
    )

    artifact_dir = tmp_path / "artifacts_fetch"
    log_path = artifact_dir / "rich_e2e_cli.log"
    html_path = artifact_dir / "rich_e2e_cli.html"
    logger.finish(
        {
            "exit_code": (result.exit_code, "Typer"),
            "artifact_log": (log_path, "FlowLogger"),
            "artifact_html": (html_path, "FlowLogger"),
            "rich_template": (RICH_TEMPLATE_HASH, "FlowLogger"),
        }
    )
    _export_transcripts(console, artifact_dir)

    assert log_path.exists()
    assert html_path.exists()
    log_text = console.export_text(clear=False)
    assert "Field" in log_text and "Source" in log_text
    assert "Flow progress" in log_text
    assert "Timing Snapshot" in log_text


def test_e2e_fetch_resume_logs_with_rich(monkeypatch, tmp_path: Path) -> None:
    url = "https://example.com/article"
    resume_root = tmp_path / "resume"
    done_dir = resume_root / "done_flags"
    done_dir.mkdir(parents=True)
    done_flag = done_dir / f"done_{_resume_hash(url)}.flag"
    done_flag.write_text("done", encoding="utf-8")

    console = _setup_console(monkeypatch, [mdwb_cli])
    logger = FlowLogger(console, "mdwb fetch --resume")
    logger.banner("Resume guard")
    logger.step(
        "Workspace",
        description="Seeded resume workspace so the CLI must explain why the URL is skipped.",
        inputs={"url": url, "resume_root": resume_root},
        outputs={"done_flag": done_flag},
        command=f"touch {done_flag}",
    )

    function_calls: list[str] = []
    original_status = mdwb_cli.ResumeManager.status
    original_is_complete = mdwb_cli.ResumeManager.is_complete

    def tracking_status(self: mdwb_cli.ResumeManager) -> tuple[int, int | None]:
        function_calls.append("ResumeManager.status")
        return original_status(self)

    def tracking_is_complete(self: mdwb_cli.ResumeManager, entry: str) -> bool:
        function_calls.append("ResumeManager.is_complete")
        return original_is_complete(self, entry)

    monkeypatch.setattr(mdwb_cli.ResumeManager, "status", tracking_status)
    monkeypatch.setattr(mdwb_cli.ResumeManager, "is_complete", tracking_is_complete)
    monkeypatch.setattr(mdwb_cli, "_watch_events_with_fallback", lambda *args, **kwargs: function_calls.append("_watch_events_with_fallback"))

    command = f"mdwb fetch {url} --resume --resume-root {resume_root}"
    logger.step(
        "Invoke CLI",
        description="Trigger Typer command so ResumeManager short-circuits completed entries.",
        inputs={"resume": True, "watch": True},
        command=command,
    )

    result = runner.invoke(
        mdwb_cli.cli,
        [
            "fetch",
            url,
            "--resume",
            "--resume-root",
            str(resume_root),
        ],
    )

    assert result.exit_code == 0
    assert "skipping submission" in result.output
    logger.step(
        "Results",
        description="Summarize the skip path and the functions that executed.",
        functions=function_calls,
        outputs={"exit_code": result.exit_code, "message": result.output.strip()},
        syntax_blocks=[("text", result.output)],
    )
    logger.finish({"done_flags": done_dir, "functions_recorded": len(function_calls)})

    log_text = console.export_text()
    assert "ResumeManager.status" in log_text
    assert "ResumeManager.is_complete" in log_text
    assert "skip" in log_text.lower()


def test_e2e_agents_summarize_with_rich_logging(monkeypatch, tmp_path: Path) -> None:
    console = _setup_console(monkeypatch, [agent_shared, summarize_article])
    logger = FlowLogger(console, "agents summarize")
    logger.banner("Markdown summarizer")

    called: dict[str, Any] = {}

    def fake_capture_markdown(**kwargs):  # noqa: ANN001
        called["capture_markdown"] = kwargs
        return _capture_result("# Title\n\n- [ ] Draft plan\n- [ ] Ship tests")

    def fake_summary(markdown: str, sentences: int) -> str:
        called["summarize_markdown"] = {"sentences": sentences, "markdown": markdown}
        return "Summary: Draft plan + Ship tests"

    monkeypatch.setattr(agent_shared, "capture_markdown", fake_capture_markdown)
    monkeypatch.setattr(agent_shared, "summarize_markdown", fake_summary)
    monkeypatch.setattr(
        agent_shared,
        "resolve_settings",
        lambda api_base: mdwb_cli.APISettings("http://api", None, Path("ops/warnings.jsonl")),
    )

    command = "agents summarize --job-id demo-job --sentences 3"
    logger.step(
        "Invoke CLI",
        description="Call summarize_article CLI to reuse a job and emit Rich summaries.",
        inputs={"job_id": "demo-job", "sentences": 3},
        command=command,
    )

    result = runner.invoke(summarize_article.cli, ["--job-id", "demo-job", "--sentences", "3"])
    assert result.exit_code == 0
    assert called["capture_markdown"]["job_id"] == "demo-job"
    assert called["summarize_markdown"]["sentences"] == 3

    logger.step(
        "Outputs",
        description="Captured Markdown + generated summary for downstream agents.",
        functions=["shared.capture_markdown", "shared.summarize_markdown"],
        outputs={
            "sentences": (called["summarize_markdown"]["sentences"], "agent_shared.summarize_markdown"),
            "markdown_lines": (
                len(called["summarize_markdown"]["markdown"].splitlines()),
                "agent_shared.capture_markdown",
            ),
        },
        syntax_blocks=[
            ("markdown", called["summarize_markdown"]["markdown"]),
            ("text", result.output),
        ],
    )

    artifact_dir = tmp_path / "artifacts_agents"
    log_path = artifact_dir / "rich_e2e_cli_agents.log"
    html_path = artifact_dir / "rich_e2e_cli_agents.html"
    logger.finish(
        {
            "job_id": ("demo-job", "agent_shared"),
            "summary_len": (len(result.output.splitlines()), "Typer"),
            "artifact_log": (log_path, "FlowLogger"),
            "artifact_html": (html_path, "FlowLogger"),
            "rich_template": (RICH_TEMPLATE_HASH, "FlowLogger"),
        }
    )
    _export_transcripts(console, artifact_dir, stem="rich_e2e_cli_agents")

    log_text = console.export_text(clear=False)
    assert "shared.capture_markdown" in log_text
    assert "Summary for job" in log_text
    assert log_path.exists() and html_path.exists()
    assert "Flow progress" in log_text


def test_e2e_agents_generate_todos_with_rich_logging(monkeypatch, tmp_path: Path) -> None:
    console = _setup_console(monkeypatch, [agent_shared, generate_todos])
    logger = FlowLogger(console, "agents generate_todos")
    logger.banner("TODO extraction")

    called: dict[str, Any] = {}
    todos_payload = ["Fix warnings", "Ship report"]

    def fake_capture_markdown(**kwargs):  # noqa: ANN001
        called["capture_markdown"] = kwargs
        return _capture_result("# Tasks\n\n- [ ] Fix warnings\n- [ ] Ship report")

    def fake_extract_todos(markdown: str, max_tasks: int) -> list[str]:
        called["extract_todos"] = {"markdown": markdown, "max_tasks": max_tasks}
        return todos_payload

    monkeypatch.setattr(agent_shared, "capture_markdown", fake_capture_markdown)
    monkeypatch.setattr(agent_shared, "extract_todos", fake_extract_todos)
    monkeypatch.setattr(
        agent_shared,
        "resolve_settings",
        lambda api_base: mdwb_cli.APISettings("http://api", None, Path("ops/warnings.jsonl")),
    )

    command = "agents generate-todos --job-id demo-job --limit 2"
    logger.step(
        "Invoke CLI",
        description="Run the TODO generator so the CLI enumerates actionable tasks.",
        inputs={"job_id": "demo-job", "limit": 2},
        command=command,
    )

    result = runner.invoke(
        generate_todos.cli,
        ["--job-id", "demo-job", "--limit", "2"],
    )

    assert result.exit_code == 0
    assert called["capture_markdown"]["job_id"] == "demo-job"
    assert called["extract_todos"]["max_tasks"] == 2

    logger.step(
        "Outputs",
        description="Show the derived TODO items with numbered formatting.",
        functions=["shared.capture_markdown", "shared.extract_todos"],
        outputs={
            "todos": (", ".join(todos_payload), "agent_shared.extract_todos"),
            "count": (len(todos_payload), "FlowLogger"),
        },
        syntax_blocks=[("text", result.output)],
    )

    artifact_dir = tmp_path / "artifacts_todos"
    log_path = artifact_dir / "rich_e2e_cli_todos.log"
    html_path = artifact_dir / "rich_e2e_cli_todos.html"
    logger.finish(
        {
            "job_id": ("demo-job", "agent_shared"),
            "todo_count": (len(todos_payload), "FlowLogger"),
            "artifact_log": (log_path, "FlowLogger"),
            "artifact_html": (html_path, "FlowLogger"),
            "rich_template": (RICH_TEMPLATE_HASH, "FlowLogger"),
        }
    )
    _export_transcripts(console, artifact_dir, stem="rich_e2e_cli_todos")

    log_text = console.export_text(clear=False)
    assert "TODOs for job" in log_text
    assert "shared.extract_todos" in log_text
    assert log_path.exists() and html_path.exists()


def test_e2e_warning_tail_and_diag_with_rich_logging(monkeypatch, tmp_path: Path) -> None:
    console = _setup_console(monkeypatch, [mdwb_cli])
    logger = FlowLogger(console, "warnings tail + diag")
    logger.banner("Warning triage and manifest diagnostics")

    log_path = tmp_path / "warnings.jsonl"
    record = {
        "timestamp": "2025-11-08T08:00:00Z",
        "job_id": "run-1",
        "warnings": [
            {"code": "canvas-heavy", "message": "Many canvas elements", "count": 4, "threshold": 3},
        ],
        "sweep_stats": {"shrink_events": 1, "retry_attempts": 0, "overlap_pairs": 3, "overlap_match_ratio": 0.82},
        "validation_failures": ["Tile checksum mismatch"],
        "blocklist_hits": {"#banner": 2},
    }
    log_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    logger.step(
        "Seed log",
        description="Write a structured warning entry to exercise the Rich tail output.",
        outputs={"log_path": (log_path, "tmp_path")},
        syntax_blocks=[("json", json.dumps(record, indent=2))],
    )

    command = f"mdwb warnings tail --count 1 --json --log-path {log_path}"
    logger.step(
        "Invoke CLI",
        description="Call warnings tail in JSON mode for deterministic parsing.",
        inputs={"count": (1, "cli flag"), "json": (True, "cli flag")},
        command=command,
    )

    result = runner.invoke(
        mdwb_cli.cli,
        [
            "warnings",
            "tail",
            "--count",
            "1",
            "--json",
            "--log-path",
            str(log_path),
        ],
    )

    assert result.exit_code == 0
    warning_payload = json.loads(log_path.read_text().splitlines()[0])
    logger.step(
        "Warnings tail output",
        description="Verify that canvas-heavy warnings and validation details are surfaced.",
        outputs={
            "exit_code": (result.exit_code, "warnings tail"),
            "warning_codes": ([w["code"] for w in warning_payload.get("warnings", [])], "warnings tail"),
        },
        syntax_blocks=[("json", result.output)],
    )

    snapshot = {
        "id": "run-1",
        "url": "https://example.com",
        "state": "DONE",
        "progress": {"done": 5, "total": 5},
    }
    manifest = {
        "environment": {"cft_label": "Stable-1", "cft_version": "chrome-130"},
        "warnings": record["warnings"],
        "blocklist_hits": record["blocklist_hits"],
    }
    diag_responses = {
        "/jobs/run-1": DummyResponse(200, payload=snapshot),
        "/jobs/run-1/manifest.json": DummyResponse(200, payload=manifest),
    }

    class _DiagClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get(self, path: str):
            self.calls.append(path)
            response = diag_responses.get(path)
            if response is None:
                raise AssertionError(f"Unexpected GET {path}")
            return response

        def close(self) -> None:  # pragma: no cover - stub
            return None

    diag_client = _DiagClient()

    @contextmanager
    def fake_client_ctx(*_args, **_kwargs):
        yield diag_client

    monkeypatch.setattr(mdwb_cli, "_client_ctx", fake_client_ctx)
    monkeypatch.setattr(
        mdwb_cli,
        "_resolve_settings",
        lambda api_base: mdwb_cli.APISettings("http://api", None, Path("ops/warnings.jsonl")),
    )

    diag_command = "mdwb diag run-1 --json"
    logger.step(
        "Diag CLI",
        description="Fetch manifest+environment for the warned job to correlate anomalies.",
        inputs={"job_id": ("run-1", "warnings payload"), "json": (True, "cli flag")},
        command=diag_command,
        functions=["_client_ctx", "client.get", "_print_diag_report"],
    )

    diag_result = runner.invoke(mdwb_cli.cli, ["diag", "run-1", "--json"])
    assert diag_result.exit_code == 0
    diag_payload = json.loads(diag_result.output)

    logger.step(
        "Diag output",
        description="Log manifest diagnostics with overlap + warning metrics.",
        outputs={
            "manifest_source": (diag_payload.get("manifest_source"), "mdwb diag"),
            "warning_count": (len(diag_payload.get("manifest", {}).get("warnings", [])), "mdwb diag"),
            "blocklist_hits": (diag_payload.get("manifest", {}).get("blocklist_hits"), "mdwb diag"),
        },
        syntax_blocks=[("json", diag_result.output)],
    )

    artifact_dir = tmp_path / "artifacts_warnings"
    log_artifact = artifact_dir / "rich_e2e_cli_warnings.log"
    html_artifact = artifact_dir / "rich_e2e_cli_warnings.html"
    logger.finish(
        {
            "records": (1, "warnings tail"),
            "diag_calls": (", ".join(diag_client.calls), "mdwb diag"),
            "artifact_log": (log_artifact, "FlowLogger"),
            "artifact_html": (html_artifact, "FlowLogger"),
            "rich_template": (RICH_TEMPLATE_HASH, "FlowLogger"),
        }
    )
    _export_transcripts(console, artifact_dir, stem="rich_e2e_cli_warnings")

    log_text = console.export_text(clear=False)
    assert "canvas-heavy" in log_text
    assert "validation" in log_text.lower()
    assert "Flow progress" in log_text
    assert log_artifact.exists() and html_artifact.exists()
