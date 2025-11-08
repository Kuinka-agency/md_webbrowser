from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from scripts.agents import shared

cli = typer.Typer(help="Capture Markdown and emit actionable TODO items.")
console = Console()


@cli.command()
def todos(
    url: str = typer.Option(
        "",
        "--url",
        help="URL to capture. Optional when --job-id is provided.",
    ),
    job_id: str = typer.Option(
        "",
        "--job-id",
        help="Reuse an existing job instead of starting a new capture.",
    ),
    api_base: Optional[str] = typer.Option(None, help="Override API base URL."),
    profile: Optional[str] = typer.Option(None, help="Browser profile id."),
    ocr_policy: Optional[str] = typer.Option(None, help="OCR policy id."),
    limit: int = typer.Option(8, min=1, max=20, help="Maximum TODO items to emit."),
    json_output: bool = typer.Option(False, "--json/--no-json", help="Emit JSON instead of text."),
    http2: bool = typer.Option(True, "--http2/--no-http2"),
    poll_interval: float = typer.Option(2.0, help="Seconds between polling /jobs/{id}."),
    timeout: float = typer.Option(300.0, help="Maximum seconds to wait for completion."),
) -> None:
    """Capture Markdown (or reuse a job) and print actionable bullet items."""

    settings = shared.resolve_settings(api_base)
    capture = shared.capture_markdown(
        url=url or None,
        job_id=job_id or None,
        settings=settings,
        http2=http2,
        profile=profile,
        ocr_policy=ocr_policy,
        poll_interval=poll_interval,
        timeout=timeout,
    )
    todos = shared.extract_todos(capture.markdown, max_tasks=limit)
    if json_output:
        console.print_json(data={"job_id": capture.job_id, "todos": todos})
        return
    if not todos:
        console.print("[yellow]No TODO-style bullets found in the Markdown.[/]")
        return
    console.rule(f"TODOs for job {capture.job_id}")
    for idx, item in enumerate(todos, start=1):
        console.print(f"{idx}. {item}")


def main() -> None:  # pragma: no cover - Typer entry
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()

