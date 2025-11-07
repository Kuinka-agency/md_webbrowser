from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.capture import CaptureManifest, CaptureResult, ScrollPolicy, SweepStats
from app.jobs import JobManager, JobState
from app.schemas import JobCreateRequest
from app.store import StorageConfig, Store


async def _fake_runner(*, job_id: str, url: str, store: Store, config=None):  # noqa: ANN001
    manifest = CaptureManifest(
        url=url,
        cft_label="Stable-1",
        cft_version="chrome-130",
        playwright_channel="chrome",
        playwright_version="1.55.0",
        browser_transport="cdp",
        screenshot_style_hash="demo",
        viewport_width=1280,
        viewport_height=2000,
        device_scale_factor=2,
        long_side_px=1288,
        capture_ms=100,
        tiles_total=1,
        scroll_policy=ScrollPolicy(
            settle_ms=300,
            max_steps=10,
            viewport_overlap_px=120,
            viewport_step_px=1080,
        ),
        sweep_stats=SweepStats(
            sweep_count=1,
            total_scroll_height=2000,
            shrink_events=0,
            retry_attempts=0,
            overlap_pairs=0,
            overlap_match_ratio=0.0,
        ),
        user_agent="Demo",
        shrink_retry_limit=2,
        blocklist_version="demo",
        blocklist_hits={},
        warnings=[],
    )
    result = CaptureResult(tiles=[], manifest=manifest)
    await asyncio.sleep(0)
    return result, []


@pytest.mark.asyncio
async def test_job_manager_broadcasts_snapshots(tmp_path: Path):
    config = StorageConfig(cache_root=tmp_path / "cache", db_path=tmp_path / "runs.db")
    store = Store(config)
    manager = JobManager(store=store, runner=_fake_runner)
    request = JobCreateRequest(url="https://example.com")
    snapshot = await manager.create_job(request)
    job_id = snapshot["id"]
    queue = manager.subscribe(job_id)

    seen_states: list[str] = []
    while True:
        update = await asyncio.wait_for(queue.get(), timeout=1)
        seen_states.append(update["state"])
        if update["state"] == JobState.DONE.value:
            break

    assert JobState.BROWSER_STARTING.value in seen_states
    assert seen_states[-1] == JobState.DONE.value

    manager.unsubscribe(job_id, queue)
