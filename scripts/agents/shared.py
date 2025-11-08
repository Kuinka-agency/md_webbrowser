from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional, Sequence

import typer
from rich.console import Console

from scripts import mdwb_cli

console = Console()

TERMINAL_STATES = {"DONE", "FAILED", "CANCELLED"}


@dataclass(slots=True)
class CaptureResult:
    job_id: str
    snapshot: dict
    markdown: str


def resolve_settings(api_base: Optional[str]) -> mdwb_cli.APISettings:
    """Reuse mdwb_cli's settings resolver."""

    return mdwb_cli._resolve_settings(api_base)


def submit_job(
    url: str,
    settings: mdwb_cli.APISettings,
    *,
    http2: bool = True,
    profile: Optional[str] = None,
    ocr_policy: Optional[str] = None,
) -> dict:
    """Submit a capture job and return the JSON payload."""

    with mdwb_cli._client_ctx(settings, http2=http2) as client:
        payload: dict[str, object] = {"url": url}
        if profile:
            payload["profile_id"] = profile
        if ocr_policy:
            payload["ocr"] = {"policy": ocr_policy}
        response = client.post("/jobs", json=payload)
        response.raise_for_status()
        job = response.json()
        console.print(f"[green]Submitted job {job.get('id')} for {url}[/]")
        return job


def wait_for_completion(
    job_id: str,
    settings: mdwb_cli.APISettings,
    *,
    http2: bool = True,
    poll_interval: float = 2.0,
    timeout: float = 300.0,
) -> dict:
    """Poll /jobs/{id} until the job reaches a terminal state."""

    deadline = time.monotonic() + timeout
    with mdwb_cli._client_ctx(settings, http2=http2) as client:
        while True:
            response = client.get(f"/jobs/{job_id}")
            response.raise_for_status()
            snapshot = response.json()
            state = snapshot.get("state")
            if state in TERMINAL_STATES:
                return snapshot
            if time.monotonic() > deadline:
                raise TimeoutError(f"Job {job_id} did not finish within {timeout} seconds.")
            time.sleep(poll_interval)


def fetch_markdown(
    job_id: str,
    settings: mdwb_cli.APISettings,
    *,
    http2: bool = True,
) -> str:
    """Download the final Markdown artifact for a job."""

    with mdwb_cli._client_ctx(settings, http2=http2) as client:
        response = client.get(f"/jobs/{job_id}/result.md")
        response.raise_for_status()
        return response.text


def capture_markdown(
    *,
    url: Optional[str],
    job_id: Optional[str],
    settings: mdwb_cli.APISettings,
    http2: bool = True,
    profile: Optional[str] = None,
    ocr_policy: Optional[str] = None,
    poll_interval: float = 2.0,
    timeout: float = 300.0,
) -> CaptureResult:
    """Ensure final Markdown is available by submitting or reusing a job."""

    if not url and not job_id:
        raise typer.BadParameter("Provide either --url or --job-id.", param_hint="--url/--job-id")

    if url and job_id:
        console.print("[yellow]Both URL and job id provided; using the existing job id.[/]")

    effective_job_id = job_id
    snapshot: dict

    if effective_job_id is None:
        job = submit_job(url=url or "", settings=settings, http2=http2, profile=profile, ocr_policy=ocr_policy)
        job_id_value = job.get("id")
        if not job_id_value:
            raise RuntimeError("Capture job did not return a job id.")
        effective_job_id = str(job_id_value)

    snapshot = wait_for_completion(
        effective_job_id,
        settings,
        http2=http2,
        poll_interval=poll_interval,
        timeout=timeout,
    )

    state = snapshot.get("state")
    if state != "DONE":
        manifest = snapshot.get("manifest")
        raise RuntimeError(f"Job {effective_job_id} finished in state {state}: {manifest or snapshot}")

    markdown = fetch_markdown(effective_job_id, settings, http2=http2)
    return CaptureResult(job_id=effective_job_id, snapshot=snapshot, markdown=markdown)


def _strip_markdown(markdown: str) -> str:
    """Coarsely strip Markdown to help heuristics."""

    text = re.sub(r"```.*?```", " ", markdown, flags=re.S)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^>+\s*", "", text, flags=re.M)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"~{2}([^~]+)~{2}", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def summarize_markdown(markdown: str, *, sentences: int = 5) -> str:
    """Return the first N sentences from the Markdown body."""

    plain = _strip_markdown(markdown)
    if not plain:
        return ""
    chunks = re.split(r"(?<=[.!?])\s+", plain)
    if not chunks:
        return plain
    summary = " ".join(chunks[:sentences]).strip()
    if not summary:
        return plain
    return summary


def _normalize_task_line(line: str) -> Optional[str]:
    stripped = line.strip()
    lower = stripped.lower()
    if not stripped:
        return None
    checkbox_prefixes = ("- [ ]", "- [x]", "- [X]")
    for prefix in checkbox_prefixes:
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip()
    if stripped.startswith(("- ", "* ")):
        return stripped[2:].strip()
    keyword_prefixes = ("todo:", "task:", "next:", "action:")
    for prefix in keyword_prefixes:
        if lower.startswith(prefix):
            return stripped[len(prefix) :].strip()
    return None


def extract_todos(
    markdown: str,
    *,
    max_tasks: int = 8,
    heading_keywords: Optional[Sequence[str]] = None,
) -> list[str]:
    """Extract actionable bullet lines or TODO sections from Markdown."""

    keywords = tuple((heading_keywords or ("todo", "task", "next", "action", "action-item")))
    tasks: list[str] = []
    seen: set[str] = set()
    capture_from_heading = False

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            lower = line.lower()
            capture_from_heading = any(keyword in lower for keyword in keywords)
            continue
        candidate = _normalize_task_line(line)
        if candidate:
            cleaned = candidate.rstrip(".")
            if cleaned and cleaned not in seen:
                tasks.append(cleaned)
                seen.add(cleaned)
        elif capture_from_heading and line:
            cleaned = line.lstrip("-*0123456789. ").strip()
            if cleaned and cleaned not in seen:
                tasks.append(cleaned)
                seen.add(cleaned)
        if len(tasks) >= max_tasks:
            break
    return tasks
