"""Job state machine and models for capture requests."""

from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict


class JobState(str, Enum):
    """Enumerated lifecycle states for a capture job."""

    BROWSER_STARTING = "BROWSER_STARTING"
    NAVIGATING = "NAVIGATING"
    SCROLLING = "SCROLLING"
    CAPTURING = "CAPTURING"
    TILING = "TILING"
    OCR_SUBMITTING = "OCR_SUBMITTING"
    OCR_WAITING = "OCR_WAITING"
    STITCHING = "STITCHING"
    DONE = "DONE"
    FAILED = "FAILED"


class JobSnapshot(TypedDict, total=False):
    """Serialized view of a job for API responses and SSE events."""

    id: str
    state: JobState
    url: str
    progress: dict[str, int]
    manifest_path: str
    error: str | None


def build_initial_snapshot(url: str, *, job_id: str) -> JobSnapshot:
    """Construct a basic snapshot stub used before persistence wiring exists."""

    return JobSnapshot(
        id=job_id,
        url=url,
        state=JobState.BROWSER_STARTING,
        progress={"done": 0, "total": 0},
        manifest_path="",
        error=None,
    )
