from app.schemas import (
    ConcurrencyWindow,
    ManifestEnvironment,
    ManifestMetadata,
    ManifestWarning,
    ViewportSettings,
)
from app.warning_log import append_warning_log


def _demo_manifest(with_warning: bool = True, with_hits: bool = False) -> ManifestMetadata:
    env = ManifestEnvironment(
        cft_version="chrome-130",
        cft_label="Stable-1",
        playwright_channel="cft",
        playwright_version="1.55.0",
        browser_transport="cdp",
        viewport=ViewportSettings(width=1280, height=2000, device_scale_factor=2, color_scheme="light"),
        viewport_overlap_px=120,
        tile_overlap_px=120,
        scroll_settle_ms=350,
        max_viewport_sweeps=200,
        screenshot_style_hash="demo",
        screenshot_mask_selectors=(),
        ocr_model="olmOCR-2-7B-1025-FP8",
        ocr_use_fp8=True,
        ocr_concurrency=ConcurrencyWindow(min=2, max=8),
    )
    manifest = ManifestMetadata(environment=env)
    if with_warning:
        manifest.warnings.append(
            ManifestWarning(code="canvas-heavy", message="demo", count=5, threshold=3)
        )
    if with_hits:
        manifest.blocklist_hits = {"#cookie": 2}
    manifest.blocklist_version = "2025-11-07"
    return manifest


def test_append_warning_log_writes_file(monkeypatch, tmp_path):
    log_path = tmp_path / "warnings.jsonl"

    class DummyLogging:
        warning_log_path = log_path

    class DummySettings:
        logging = DummyLogging()

    monkeypatch.setattr("app.warning_log.get_settings", lambda: DummySettings())

    append_warning_log(job_id="run-1", url="https://example.com", manifest=_demo_manifest())

    assert log_path.exists()
    content = log_path.read_text().strip()
    assert "canvas-heavy" in content


def test_append_warning_log_skips_when_empty(monkeypatch, tmp_path):
    log_path = tmp_path / "warnings.jsonl"

    class DummyLogging:
        warning_log_path = log_path

    class DummySettings:
        logging = DummyLogging()

    monkeypatch.setattr("app.warning_log.get_settings", lambda: DummySettings())

    append_warning_log(job_id="run-2", url="https://example.com", manifest=_demo_manifest(with_warning=False, with_hits=False))

    assert not log_path.exists()
