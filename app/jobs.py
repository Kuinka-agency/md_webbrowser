"""Job orchestration helpers for capture requests."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
from importlib import metadata
from typing import Any, Awaitable, Callable, Dict, List, Mapping, TypedDict
from uuid import uuid4

import hashlib
import hmac
import json
import logging

import httpx

from app.capture import CaptureConfig, CaptureResult, capture_tiles
from app.dom_links import extract_links_from_dom, serialize_links
from app.schemas import JobCreateRequest, ManifestMetadata
from app.settings import Settings, settings as global_settings
from app.store import Store, build_store
from app.warning_log import append_warning_log

LOGGER = logging.getLogger(__name__)

WebhookSender = Callable[[str, dict[str, Any]], Awaitable[None]]
_EVENT_HISTORY_LIMIT = 500

try:  # Playwright may be missing in some CI environments
    PLAYWRIGHT_VERSION = metadata.version("playwright")
except metadata.PackageNotFoundError:  # pragma: no cover - dev fallback
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
    error: str | None


def build_initial_snapshot(
    url: str,
    *,
    job_id: str,
    settings: Settings | None = None,
) -> JobSnapshot:
    """Construct a baseline snapshot before capture begins."""

    manifest = None
    active_settings = settings or global_settings
    if active_settings:
        manifest = ManifestMetadata(
            environment=active_settings.manifest_environment(playwright_version=PLAYWRIGHT_VERSION)
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
    """In-memory job registry backed by Store persistence."""

    def __init__(
        self,
        *,
        store: Store | None = None,
        runner: RunnerType | None = None,
        webhook_sender: WebhookSender | None = None,
    ) -> None:
        self.store = store or build_store()
        self._runner = runner or execute_capture_job
        self._snapshots: Dict[str, JobSnapshot] = {}
        self._tasks: Dict[str, asyncio.Task[None]] = {}
        self._subscribers: Dict[str, List[asyncio.Queue[JobSnapshot]]] = {}
        self._event_logs: Dict[str, List[dict[str, Any]]] = {}
        self._event_sequences: Dict[str, int] = {}
        self._event_subscribers: Dict[str, List[asyncio.Queue[dict[str, Any]]]] = {}
        self._webhooks: Dict[str, List[dict[str, Any]]] = {}
        self._webhook_sender = webhook_sender or _default_webhook_sender

    async def create_job(self, request: JobCreateRequest) -> JobSnapshot:
        job_id = uuid4().hex
        snapshot = build_initial_snapshot(url=request.url, job_id=job_id)
        self._snapshots[job_id] = snapshot.copy()
        self._event_logs[job_id] = []
        self._event_sequences[job_id] = 0
        self._broadcast(job_id)
        task = asyncio.create_task(self._run_job(job_id=job_id, url=request.url))
        self._tasks[job_id] = task
        return snapshot.copy()

    def get_snapshot(self, job_id: str) -> JobSnapshot:
        snapshot = self._snapshots.get(job_id)
        if snapshot is None:
            raise KeyError(f"Job {job_id} not found")
        return snapshot.copy()

    def subscribe(self, job_id: str) -> asyncio.Queue[JobSnapshot]:
        if job_id not in self._snapshots:
            raise KeyError(f"Job {job_id} not found")
        queue: asyncio.Queue[JobSnapshot] = asyncio.Queue()
        queue.put_nowait(self._snapshot_payload(job_id))
        self._subscribers.setdefault(job_id, []).append(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[JobSnapshot]) -> None:
        subscribers = self._subscribers.get(job_id)
        if not subscribers:
            return
        if queue in subscribers:
            subscribers.remove(queue)
        if not subscribers:
            self._subscribers.pop(job_id, None)

    def subscribe_events(
        self, job_id: str, *, since: datetime | None = None
    ) -> tuple[list[dict[str, Any]], asyncio.Queue[dict[str, Any]]]:
        if job_id not in self._snapshots:
            raise KeyError(f"Job {job_id} not found")
        backlog = self.get_events(job_id, since=since)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._event_subscribers.setdefault(job_id, []).append(queue)
        return backlog, queue

    def unsubscribe_events(self, job_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subscribers = self._event_subscribers.get(job_id)
        if not subscribers:
            return
        if queue in subscribers:
            subscribers.remove(queue)
        if not subscribers:
            self._event_subscribers.pop(job_id, None)

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
        except Exception as exc:  # pragma: no cover - surfaced to API callers
            self._set_state(job_id, JobState.FAILED)
            self._set_error(job_id, str(exc))
            raise
        finally:
            self._tasks.pop(job_id, None)

    def _set_state(self, job_id: str, state: JobState) -> None:
        snapshot = self._snapshots.get(job_id)
        if snapshot is None:
            return
        snapshot["state"] = state
        self._broadcast(job_id)

    def _set_error(self, job_id: str, message: str | None) -> None:
        snapshot = self._snapshots.get(job_id)
        if snapshot is None:
            return
        snapshot["error"] = message
        self._broadcast(job_id)

    def get_events(
        self,
        job_id: str,
        since: datetime | None = None,
        *,
        min_sequence: int | None = None,
    ) -> List[dict[str, Any]]:
        if job_id not in self._snapshots:
            raise KeyError(f"Job {job_id} not found")
        events = self._event_logs.get(job_id, [])
        if since is None:
            if min_sequence is None:
                return [event.copy() for event in events]
            return [
                event.copy()
                for event in events
                if self._sequence_newer(event, min_sequence)
            ]
        filtered: List[dict[str, Any]] = []
        for event in events:
            parsed_ts = self._parse_timestamp(event.get("timestamp"))
            if parsed_ts and parsed_ts >= since:
                if min_sequence is not None and not self._sequence_newer(event, min_sequence):
                    continue
                filtered.append(event.copy())
        return filtered

    def register_webhook(self, job_id: str, *, url: str, events: list[str] | None = None) -> None:
        if job_id not in self._snapshots:
            raise KeyError(f"Job {job_id} not found")
        valid_states = {member.value for member in JobState}
        normalized: list[str] = []
        for entry in events or [JobState.DONE.value, JobState.FAILED.value]:
            if entry not in valid_states:
                msg = f"Unsupported job state '{entry}'"
                raise ValueError(msg)
            normalized.append(entry)
        self._webhooks.setdefault(job_id, []).append({"url": url, "events": normalized})

    def _broadcast(self, job_id: str) -> None:
        payload = self._snapshot_payload(job_id)
        self._record_event(job_id, payload)
        for queue in list(self._subscribers.get(job_id, [])):
            queue.put_nowait(payload.copy())
        self._maybe_trigger_webhooks(job_id, payload)

    def _snapshot_payload(self, job_id: str) -> JobSnapshot:
        snapshot = self._snapshots.get(job_id)
        if snapshot is None:
            raise KeyError(f"Job {job_id} not found")
        payload = snapshot.copy()
        state = payload.get("state")
        if isinstance(state, JobState):
            payload["state"] = state.value
        return payload

    def _record_event(self, job_id: str, payload: JobSnapshot) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sequence": self._event_sequences.get(job_id, 0),
            "event": "snapshot",
            "snapshot": payload,
        }
        sequence = int(entry["sequence"])
        self._event_sequences[job_id] = sequence + 1
        log = self._event_logs.setdefault(job_id, [])
        log.append(entry)
        if len(log) > _EVENT_HISTORY_LIMIT:
            del log[: len(log) - _EVENT_HISTORY_LIMIT]
        for queue in list(self._event_subscribers.get(job_id, [])):
            queue.put_nowait(entry.copy())

    def _parse_timestamp(self, raw: Any) -> datetime | None:
        if not isinstance(raw, str):
            return None
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _sequence_newer(self, event: Mapping[str, Any], min_sequence: int) -> bool:
        try:
            seq = int(event.get("sequence", -1))
        except (TypeError, ValueError):
            return False
        return seq > min_sequence

    def _maybe_trigger_webhooks(self, job_id: str, payload: JobSnapshot) -> None:
        sender = self._webhook_sender
        if sender is None:
            return
        hooks = self._webhooks.get(job_id)
        if not hooks:
            return
        state = payload.get("state")
        if not isinstance(state, str):
            return
        for hook in hooks:
            allowed = hook.get("events") or []
            if state not in allowed:
                continue
            asyncio.create_task(
                sender(
                    hook["url"],
                    {
                        "job_id": job_id,
                        "state": state,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "snapshot": payload,
                    },
                )
            )


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
        dom_snapshot = getattr(capture_result, "dom_snapshot", None)
        dom_path = None
        if dom_snapshot:
            dom_path = storage.write_dom_snapshot(job_id=job_id, html=dom_snapshot)
        write_links = getattr(storage, "write_links", None)
        if dom_path and callable(write_links):
            try:
                dom_links = extract_links_from_dom(dom_path)
                write_links(job_id=job_id, links=serialize_links(dom_links))
            except Exception as exc:  # pragma: no cover - log and continue
                LOGGER.warning("Failed to extract DOM links for %s: %s", job_id, exc)
        tile_artifacts = storage.write_tiles(job_id=job_id, tiles=capture_result.tiles)
    except Exception:
        storage.update_status(job_id=job_id, status=JobState.FAILED, finished_at=datetime.now(timezone.utc))
        raise

    storage.update_status(job_id=job_id, status=JobState.DONE, finished_at=datetime.now(timezone.utc))
    return capture_result, tile_artifacts


async def _default_webhook_sender(url: str, payload: dict[str, Any]) -> None:
    """Best-effort webhook HTTP POST without signing."""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)
    except Exception as exc:  # pragma: no cover - logging only
        LOGGER.warning("Webhook delivery to %s failed: %s", url, exc)


def build_signed_webhook_sender(secret: str, *, version: str = "v1") -> WebhookSender:
    """Return a webhook sender that signs payloads using HMAC-SHA256."""

    secret_bytes = secret.encode("utf-8")

    async def _sender(url: str, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = hmac.new(secret_bytes, body, hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-MDWB-Signature": f"{version}={signature}",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, content=body, headers=headers)
        except Exception as exc:  # pragma: no cover - logging only
            LOGGER.warning("Signed webhook delivery to %s failed: %s", url, exc)

    return _sender
