#!/usr/bin/env python3
"""Display the most recent smoke run summary/manifest pointers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import typer

DEFAULT_ROOT = Path(os.environ.get("MDWB_SMOKE_ROOT", "benchmarks/production"))


@dataclass(slots=True)
class SmokePaths:
    root: Path
    summary: Path
    manifest_index: Path
    pointer: Path
    metrics: Path
    weekly_summary: Path

    @classmethod
    def from_root(cls, root: Path) -> "SmokePaths":
        return cls(
            root=root,
            summary=root / "latest_summary.md",
            manifest_index=root / "latest_manifest_index.json",
            pointer=root / "latest.txt",
            metrics=root / "latest_metrics.json",
            weekly_summary=root / "weekly_summary.json",
        )


app = typer.Typer(help="Inspect the latest smoke run outputs (set MDWB_SMOKE_ROOT to override paths).")


def _ensure_pointer(paths: SmokePaths) -> str:
    if not paths.pointer.exists():
        typer.secho("No smoke runs have produced pointer files yet.", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    return paths.pointer.read_text(encoding="utf-8").strip()


def _format_ms(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        return f"{value:.0f}"
    return str(value)


def _load_weekly_summary(paths: SmokePaths) -> dict[str, Any]:
    if not paths.weekly_summary.exists():
        typer.secho("weekly_summary.json missing", fg=typer.colors.RED)
        raise typer.Exit(1)
    return json.loads(paths.weekly_summary.read_text(encoding="utf-8"))


def _print_weekly_summary(summary: dict[str, Any]) -> None:
    window_days = summary.get("window_days") or "?"
    generated_at = summary.get("generated_at") or "?"
    typer.secho("\n=== Weekly Summary ===", fg=typer.colors.CYAN)
    typer.echo(f"Window: last {window_days} days (generated {generated_at})")

    categories = summary.get("categories") or []
    if not categories:
        typer.secho("No category data recorded yet.", fg=typer.colors.YELLOW)
        return

    typer.echo("\n| Category | Runs | Budget (ms) | Capture p50/p95 | Total p50/p95 | Status |")
    typer.echo("| --- | --- | --- | --- | --- | --- |")
    for entry in categories:
        capture = entry.get("capture_ms") or {}
        total = entry.get("total_ms") or {}
        budget = entry.get("budget_ms")
        total_p95 = total.get("p95")
        status = "OK"
        if isinstance(budget, (int, float)) and isinstance(total_p95, (int, float)) and total_p95 > budget:
            status = "⚠️ over budget"
        typer.echo(
            "| {category} | {runs} | {budget} | {cap_p50}/{cap_p95} | {tot_p50}/{tot_p95} | {status} |".format(
                category=entry.get("name", "?"),
                runs=entry.get("runs", 0),
                budget=_format_ms(budget),
                cap_p50=_format_ms(capture.get("p50")),
                cap_p95=_format_ms(capture.get("p95")),
                tot_p50=_format_ms(total.get("p50")),
                tot_p95=_format_ms(total_p95),
                status=status,
            )
        )


@app.command()
def show(
    summary: bool = typer.Option(True, help="Include the Markdown summary (if present)."),
    manifest: bool = typer.Option(False, "--manifest/--no-manifest", help="Include manifest_index entries."),
    limit: Optional[int] = typer.Option(10, help="Limit manifest rows (None = all)."),
    metrics: bool = typer.Option(False, "--metrics/--no-metrics", help="Include aggregated metrics JSON."),
    weekly: bool = typer.Option(False, "--weekly/--no-weekly", help="Include weekly_summary data."),
    root: Optional[Path] = typer.Option(None, "--root", help="Override MDWB_SMOKE_ROOT for this invocation."),
    json_output: bool = typer.Option(
        False,
        "--json/--no-json",
        help="Emit structured JSON instead of human-readable tables.",
    ),
) -> None:
    """Print (or emit JSON for) the latest smoke summary, manifest, metrics, and weekly stats."""

    paths = SmokePaths.from_root(root or DEFAULT_ROOT)
    date_stamp = _ensure_pointer(paths)
    payload: dict[str, Any] = {"run_date": date_stamp, "root": str(paths.root)} if json_output else {}

    if not json_output:
        typer.echo(f"Latest smoke run: {date_stamp}")

    if summary:
        summary_text = None
        if not paths.summary.exists():
            typer.secho("latest_summary.md missing", fg=typer.colors.RED)
        else:
            summary_text = paths.summary.read_text(encoding="utf-8")
            if not json_output:
                typer.secho("\n=== Summary (Markdown) ===\n", fg=typer.colors.CYAN)
                typer.echo(summary_text)
        if json_output:
            payload["summary_markdown"] = summary_text

    manifest_rows: Optional[list[dict[str, Any]]] = None
    if manifest:
        if not paths.manifest_index.exists():
            typer.secho("latest_manifest_index.json missing", fg=typer.colors.RED)
            raise typer.Exit(1)
        manifest_rows = json.loads(paths.manifest_index.read_text(encoding="utf-8"))
        if limit is not None:
            manifest_rows = manifest_rows[:limit]
        if not json_output:
            typer.secho("\n=== Manifest Index ===", fg=typer.colors.CYAN)
            for row in manifest_rows:
                typer.echo(
                    " - {category}: {url} (capture_ms={capture_ms}, total_ms={total_ms})".format(
                        category=row.get("category", "?"),
                        url=row.get("url", "?"),
                        capture_ms=row.get("capture_ms"),
                        total_ms=row.get("total_ms"),
                    )
                )
        else:
            payload["manifest"] = manifest_rows

    if metrics:
        if not paths.metrics.exists():
            typer.secho("latest_metrics.json missing", fg=typer.colors.RED)
            raise typer.Exit(1)
        metrics_data = json.loads(paths.metrics.read_text(encoding="utf-8"))
        if not json_output:
            typer.secho("\n=== Aggregated Metrics ===", fg=typer.colors.CYAN)
            typer.echo(json.dumps(metrics_data, indent=2))
        else:
            payload["metrics"] = metrics_data

    if weekly:
        weekly_data = _load_weekly_summary(paths)
        if not json_output:
            _print_weekly_summary(weekly_data)
        else:
            payload["weekly_summary"] = weekly_data

    if json_output:
        typer.echo(json.dumps(payload, indent=2))


def _collect_missing(paths: SmokePaths, require_weekly: bool) -> list[str]:
    required = [
        ("pointer", paths.pointer),
        ("summary", paths.summary),
        ("manifest_index", paths.manifest_index),
        ("metrics", paths.metrics),
    ]
    if require_weekly:
        required.append(("weekly_summary", paths.weekly_summary))
    missing = [name for name, path in required if not path.exists()]
    return missing


@app.command()
def check(
    weekly: bool = typer.Option(True, "--weekly/--no-weekly", help="Require weekly_summary.json to exist."),
    root: Optional[Path] = typer.Option(None, "--root", help="Override MDWB_SMOKE_ROOT for this invocation."),
    json_output: bool = typer.Option(False, "--json/--no-json", help="Emit JSON payload instead of human text."),
) -> None:
    """Verify that the latest smoke pointer files exist (for CI/dashboards)."""

    paths = SmokePaths.from_root(root or DEFAULT_ROOT)
    missing = _collect_missing(paths, require_weekly=weekly)
    payload: dict[str, Any] = {
        "root": str(paths.root),
        "weekly_required": weekly,
        "missing": missing,
    }
    if missing:
        payload["status"] = "missing"
        if json_output:
            typer.echo(json.dumps(payload, indent=2))
        else:
            typer.secho("Missing smoke artifacts:", fg=typer.colors.RED)
            for name in missing:
                typer.echo(f" - {name}")
        raise typer.Exit(1)

    run_date = _ensure_pointer(paths)
    payload["status"] = "ok"
    payload["run_date"] = run_date
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.secho(
            f"Smoke pointers present for {run_date} (summary, manifest, metrics"
            + (", weekly" if weekly else "")
            + ").",
            fg=typer.colors.GREEN,
        )


if __name__ == "__main__":
    app()
