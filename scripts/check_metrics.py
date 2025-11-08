#!/usr/bin/env python3
"""Prometheus metrics health check for Markdown Web Browser."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

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


def _probe(metrics_url: str, timeout: float) -> None:
    with httpx.Client(timeout=timeout) as client:
        response = client.get(metrics_url)
        response.raise_for_status()


def _build_summary(results: list[dict[str, object]]) -> dict[str, object]:
    ok_count = sum(1 for row in results if row.get("ok"))
    fail_count = len(results) - ok_count
    status = "ok" if fail_count == 0 else "error"
    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok_count": ok_count,
        "failed_count": fail_count,
        "targets": results,
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
            _probe(url, timeout)
            results.append({"url": url, "ok": True})
            if not json_output:
                typer.echo(f"[OK] {url}")
        except Exception as exc:  # noqa: BLE001
            message = f"[FAIL] {url}: {exc}"
            errors.append(message)
            results.append({"url": url, "ok": False, "error": str(exc)})
            if not json_output:
                typer.echo(message)

    if errors:
        if json_output:
            typer.echo(json.dumps(_build_summary(results), indent=2))
        raise typer.Exit(code=1)
    if json_output:
        typer.echo(json.dumps(_build_summary(results), indent=2))


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
