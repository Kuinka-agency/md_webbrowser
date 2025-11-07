"""Job state machine and capture orchestration helpers."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
from importlib import metadata
from typing import Any, Awaitable, Callable, Dict, List, TypedDict
from uuid import uuid4

from app.capture import CaptureConfig, CaptureResult, capture_tiles
from app.schemas import JobCreateRequest, ManifestMetadata
from app.settings import Settings, settings as global_settings
from app.store import Store, build_store
from app.warning_log import append_warning_log

try:  # Playwright is an optional dependency in some CI environments
    PLAYWRIGHT_VERSION = metadata.version("playwright")
except metadata.PackageNotFoundError:  # pragma: no cover - development convenience
    PLAYWRIGHT_VERSION = None


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
    manifest: dict[str, object]
    artifacts: list[dict[str, object]]
    artifacts: list[dict[str, Any]]
    error: str | None


def build_initial_snapshot(
    url: str,
    *,
    job_id: str,
    settings: Settings | None = None,
) -> JobSnapshot:
    """Construct a basic snapshot stub used before persistence wiring exists."""

    manifest = None
    active_settings = settings or global_settings
    if active_settings:
        manifest = ManifestMetadata(
            environment=active_settings.manifest_environment(playwright_version=PLAYWRIGHT_VERSION),
        )

    snapshot = JobSnapshot(
        id=job_id,
        url=url,
        state=JobState.BROWSER_STARTING,
        progress={"done": 0, "total": 0},
        manifest_path="",
        error=None,
    )
    if manifest:
        snapshot["manifest"] = manifest.model_dump()
    return snapshot


RunnerType = Callable[..., Awaitable[tuple[CaptureResult, list[dict[str, object]]]]]


class JobManager:
    """Lightweight in-memory job registry backed by ``Store`` persistence."""

    def __init__(self, *, store: Store | None = None, runner: RunnerType | None = None) -> None:
        self.store = store or build_store()
        self._runner = runner or execute_capture_job
        self._snapshots: Dict[str, JobSnapshot] = {}
        self._tasks: Dict[str, asyncio.Task[None]] = {}
        self._subscribers: Dict[str, List[asyncio.Queue[JobSnapshot]]] = {}

    async def create_job(self, request: JobCreateRequest) -> JobSnapshot:
        job_id = uuid4().hex
        snapshot = build_initial_snapshot(url=request.url, job_id=job_id)
        self._snapshots[job_id] = snapshot
        self._broadcast(job_id)
        task = asyncio.create_task(self._run_job(job_id=job_id, url=request.url))
        self._tasks[job_id] = task
        return snapshot

    def get_snapshot(self, job_id: str) -> JobSnapshot:
        snapshot = self._snapshots.get(job_id)
        if not snapshot:
            raise KeyError(f"Job {job_id} not found")
        return snapshot

    async def _run_job(self, *, job_id: str, url: str) -> None:
        try:
            self._set_state(job_id, JobState.CAPTURING)
            capture_result, tile_artifacts = await self._runner(job_id=job_id, url=url, store=self.store)
            run_record = self.store.fetch_run(job_id)
            manifest_path = str(run_record.manifest_path) if run_record else ""
            snapshot = self._snapshots[job_id]
            snapshot["manifest_path"] = manifest_path
            snapshot["progress"] = {
                "done": capture_result.manifest.tiles_total,
                "total": capture_result.manifest.tiles_total,
            }
            snapshot["manifest"] = asdict(capture_result.manifest)
            snapshot["artifacts"] = tile_artifacts
            self._broadcast(job_id)
            self._set_state(job_id, JobState.DONE)
        except Exception as exc:  # pragma: no cover - surfaced to callers/logs
            self._set_state(job_id, JobState.FAILED)
            self._set_error(job_id, str(exc))
            raise
        finally:
            self._tasks.pop(job_id, None)

    def _set_state(self, job_id: str, state: JobState) -> None:
        snapshot = self._snapshots.get(job_id)
        if snapshot is not None:
            snapshot["state"] = state
        self._broadcast(job_id)

    def _set_error(self, job_id: str, message: str | None) -> None:
        snapshot = self._snapshots.get(job_id)
        if snapshot is not None:
            snapshot["error"] = message
        self._broadcast(job_id)

    def subscribe(self, job_id: str) -> asyncio.Queue[JobSnapshot]:
        if job_id not in self._snapshots:
            raise KeyError(f"Job {job_id} not found")
        queue: asyncio.Queue[JobSnapshot] = asyncio.Queue()
        self._subscribers.setdefault(job_id, []).append(queue)
        queue.put_nowait(self._snapshot_payload(job_id))
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[JobSnapshot]) -> None:
        subscribers = self._subscribers.get(job_id)
        if not subscribers:
            return
        if queue in subscribers:
            subscribers.remove(queue)
        if not subscribers:
            self._subscribers.pop(job_id, None)

    def _broadcast(self, job_id: str) -> None:
        if job_id not in self._snapshots or job_id not in self._subscribers:
            return
        payload = self._snapshot_payload(job_id)
        for queue in list(self._subscribers.get(job_id, [])):
            queue.put_nowait(payload)

    def _snapshot_payload(self, job_id: str) -> JobSnapshot:
        snapshot = self._snapshots[job_id]
        payload = snapshot.copy()
        state = payload.get("state")
        if isinstance(state, JobState):
            payload["state"] = state.value
        return payload


async def execute_capture_job(
    *,
    job_id: str,
    url: str,
    store: Store | None = None,
    config: CaptureConfig | None = None,
) -> tuple[CaptureResult, list[dict[str, object]]]:
    """Run the capture pipeline, persisting artifacts + manifest via ``Store``."""

    storage = store or build_store()
    started_at = datetime.now(timezone.utc)
    storage.allocate_run(job_id=job_id, url=url, started_at=started_at)
    storage.update_status(job_id=job_id, status=JobState.CAPTURING)

    capture_config = config or CaptureConfig(url=url)
    try:
        capture_result = await capture_tiles(capture_config)
        append_warning_log(job_id=job_id, url=url, manifest=capture_result.manifest)
        storage.write_manifest(job_id=job_id, manifest=capture_result.manifest)
        tile_artifacts = storage.write_tiles(job_id=job_id, tiles=capture_result.tiles)
    except Exception:
        storage.update_status(job_id=job_id, status=JobState.FAILED, finished_at=datetime.now(timezone.utc))
        raise

    storage.update_status(job_id=job_id, status=JobState.DONE, finished_at=datetime.now(timezone.utc))
    return capture_result, tile_artifacts
