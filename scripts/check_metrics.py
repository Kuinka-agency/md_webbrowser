#!/usr/bin/env python3
"""Prometheus metrics health check for Markdown Web Browser."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import httpx
import typer
from decouple import Config as DecoupleConfig, RepositoryEnv

cli = typer.Typer(help="Ping the Prometheus metrics endpoints and fail when unreachable.")


def _load_config() -> DecoupleConfig:
    env_path = Path(".env")
    if env_path.exists():
        target = env_path
    else:
        fallback = env_path.with_suffix(env_path.suffix + ".example") if env_path.suffix else Path(".env.example")
        target = fallback if fallback.exists() else env_path
    return DecoupleConfig(RepositoryEnv(str(target)))


def _default_api_base(cfg: DecoupleConfig) -> str:
    return cfg("API_BASE_URL", default="http://localhost:8000").rstrip("/")


def _default_exporter_port(cfg: DecoupleConfig) -> int:
    return cfg("PROMETHEUS_PORT", cast=int, default=9000)


def _probe(metrics_url: str, timeout: float) -> float:
    start = time.perf_counter()
    with httpx.Client(timeout=timeout) as client:
        response = client.get(metrics_url)
        response.raise_for_status()
    end = time.perf_counter()
    return (end - start) * 1000.0


def _build_summary(results: list[dict[str, object]]) -> dict[str, object]:
    ok_count = sum(1 for row in results if row.get("ok"))
    fail_count = len(results) - ok_count
    status = "ok" if fail_count == 0 else "error"
    total_duration = sum(row.get("duration_ms", 0.0) or 0.0 for row in results)
    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok_count": ok_count,
        "failed_count": fail_count,
        "total_duration_ms": total_duration,
        "targets": results,
    }


def _evaluate_weekly_summary(summary_path: Path) -> tuple[bool, dict[str, object]]:
    if not summary_path.exists():
        raise FileNotFoundError(f"weekly summary not found: {summary_path}")
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for entry in data.get("categories", []):
        name = entry.get("name", "?")
        slo = entry.get("slo") or {}
        if not isinstance(slo, dict):
            continue
        if slo.get("capture_ok") is False:
            failures.append(
                f"{name}: capture p99 {slo.get('capture_p99_ms')} > budget {slo.get('capture_budget_ms')}"
            )
        if slo.get("ocr_ok") is False:
            failures.append(
                f"{name}: OCR p99 {slo.get('ocr_p99_ms')} > budget {slo.get('ocr_budget_ms')}"
            )
    status = "ok" if not failures else "error"
    return status == "ok", {
        "status": status,
        "summary_path": str(summary_path),
        "failures": failures,
    }


@cli.command()
def run_check(
    api_base: str | None = typer.Option(
        None,
        help="Override API_BASE_URL (defaults to value from .env).",
    ),
    exporter_host: str = typer.Option(
        "localhost",
        help="Host to use when probing the standalone exporter on PROMETHEUS_PORT.",
    ),
    exporter_port: int | None = typer.Option(
        None,
        help="Override PROMETHEUS_PORT (defaults to value from .env).",
    ),
    exporter_url: str | None = typer.Option(
        None,
        help="Full URL for exporter metrics (takes precedence over host/port).",
    ),
    include_exporter: bool = typer.Option(
        True,
        "--include-exporter/--no-include-exporter",
        help="Whether to probe the standalone exporter in addition to /metrics on the API base.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json/--no-json",
        help="Emit machine-readable output summarizing each target.",
    ),
    timeout: float = typer.Option(5.0, help="HTTP timeout per request (seconds)."),
    check_weekly: bool = typer.Option(
        False,
        "--check-weekly/--skip-weekly",
        help="Validate weekly SLO summary in addition to metrics probes.",
    ),
    weekly_summary: Path = typer.Option(
        Path("benchmarks/production/weekly_summary.json"),
        help="Path to weekly_summary.json (used when --check-weekly is enabled).",
    ),
) -> None:
    """Check Prometheus metrics endpoints and exit non-zero when unreachable."""

    cfg = _load_config()
    base = (api_base or _default_api_base(cfg)).rstrip("/")
    port = exporter_port if exporter_port is not None else _default_exporter_port(cfg)

    targets: list[str] = [f"{base}/metrics"]
    if include_exporter:
        if exporter_url:
            targets.append(exporter_url.rstrip("/"))
        elif port > 0:
            targets.append(f"http://{exporter_host}:{port}/metrics")

    errors: list[str] = []
    results: list[dict[str, object]] = []
    for url in targets:
        try:
            duration_ms = _probe(url, timeout)
            results.append({"url": url, "ok": True, "duration_ms": duration_ms})
            if not json_output:
                typer.echo(f"[OK] {url} ({duration_ms:.1f} ms)")
        except Exception as exc:  # noqa: BLE001
            message = f"[FAIL] {url}: {exc}"
            errors.append(message)
            results.append({"url": url, "ok": False, "error": str(exc)})
            if not json_output:
                typer.echo(message)

    weekly_result: dict[str, object] | None = None
    if check_weekly:
        try:
            ok, weekly_result = _evaluate_weekly_summary(weekly_summary)
            if ok:
                if not json_output:
                    typer.echo(f"[OK] Weekly SLO: {weekly_summary}")
            else:
                failures = []
                if isinstance(weekly_result, Mapping):
                    raw = weekly_result.get("failures") or []
                    if isinstance(raw, list):
                        failures = [str(line) for line in raw]
                message = "[FAIL] Weekly SLO violations:\n" + "\n".join(f"- {line}" for line in failures or ["unknown"])
                errors.append(message)
                if not json_output:
                    typer.echo(message)
        except Exception as exc:  # noqa: BLE001
            message = f"[FAIL] Weekly SLO check failed: {exc}"
            errors.append(message)
            if not json_output:
                typer.echo(message)

    if errors:
        if json_output:
            payload = _build_summary(results)
            if weekly_result is not None:
                payload["weekly"] = weekly_result
            typer.echo(json.dumps(payload, indent=2))
        raise typer.Exit(code=1)
    if json_output:
        payload = _build_summary(results)
        if weekly_result is not None:
            payload["weekly"] = weekly_result
        typer.echo(json.dumps(payload, indent=2))


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
