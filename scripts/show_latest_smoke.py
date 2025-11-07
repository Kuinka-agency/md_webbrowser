#!/usr/bin/env python3
"""Display the most recent smoke run summary/manifest pointers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

ROOT = Path("benchmarks/production")
SUMMARY_PATH = ROOT / "latest_summary.md"
MANIFEST_INDEX_PATH = ROOT / "latest_manifest_index.json"
POINTER_PATH = ROOT / "latest.txt"
METRICS_PATH = ROOT / "latest_metrics.json"

app = typer.Typer(help="Inspect the latest smoke run outputs.")


def _ensure_pointer() -> str:
    if not POINTER_PATH.exists():
        typer.secho("No smoke runs have produced pointer files yet.", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    return POINTER_PATH.read_text(encoding="utf-8").strip()


@app.command()
def show(
    summary: bool = typer.Option(True, help="Print the Markdown summary."),
    manifest: bool = typer.Option(False, "--manifest/--no-manifest", help="Print manifest_index entries."),
    limit: Optional[int] = typer.Option(10, help="Limit manifest rows (None = all)."),
    metrics: bool = typer.Option(False, "--metrics/--no-metrics", help="Print the aggregated p95 metrics JSON."),
) -> None:
    """Print the latest smoke summary and/or manifest index."""

    date_stamp = _ensure_pointer()
    typer.echo(f"Latest smoke run: {date_stamp}")
    if summary:
        if not SUMMARY_PATH.exists():
            typer.secho("latest_summary.md missing", fg=typer.colors.RED)
        else:
            typer.secho("\n=== Summary (Markdown) ===\n", fg=typer.colors.CYAN)
            typer.echo(SUMMARY_PATH.read_text(encoding="utf-8"))
    if manifest:
        if not MANIFEST_INDEX_PATH.exists():
            typer.secho("latest_manifest_index.json missing", fg=typer.colors.RED)
            raise typer.Exit(1)
        rows: list[dict] = json.loads(MANIFEST_INDEX_PATH.read_text(encoding="utf-8"))
        typer.secho("\n=== Manifest Index ===", fg=typer.colors.CYAN)
        if limit is not None:
            rows = rows[:limit]
        for row in rows:
            typer.echo(
                " - {category}: {url} (capture_ms={capture_ms}, total_ms={total_ms})".format(
                    category=row.get("category", "?"),
                    url=row.get("url", "?"),
                    capture_ms=row.get("capture_ms"),
                    total_ms=row.get("total_ms"),
                )
            )
    if metrics:
        if not METRICS_PATH.exists():
            typer.secho("latest_metrics.json missing", fg=typer.colors.RED)
            raise typer.Exit(1)
        data = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        typer.secho("\n=== Aggregated Metrics ===", fg=typer.colors.CYAN)
        typer.echo(json.dumps(data, indent=2))


if __name__ == "__main__":
    app()
