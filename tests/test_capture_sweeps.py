from __future__ import annotations

from typing import Any, Iterator, Sequence, cast

import pytest

import app.capture as capture_module
from app.blocklist import BlocklistConfig
from app.capture import CaptureConfig, _perform_viewport_sweeps  # type: ignore[attr-defined]
from app.capture_warnings import CaptureWarningEntry
from app.settings import WarningSettings
from app.tiler import TileSlice


class _FakeLocator:
    def __init__(self, selector: str) -> None:
        self.selector = selector


class _FakePage:
    def __init__(self, scroll_heights: Sequence[int], dom_html: str = "<html></html>") -> None:
        self._heights: Iterator[int] = iter(scroll_heights)
        self.dom_html = dom_html
        self.user_agent = "FakeAgent/1.0"
        self.scroll_calls: list[int] = []
        self.screenshot_calls = 0

    async def add_init_script(self, script: str) -> None:  # noqa: ARG002
        return None

    async def add_style_tag(self, content: str) -> None:  # noqa: ARG002
        return None

    async def goto(self, url: str, wait_until: str) -> None:  # noqa: ARG002
        return None

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(selector)

    async def screenshot(self, **kwargs: Any) -> bytes:  # noqa: ARG002
        self.screenshot_calls += 1
        return b"fake-png"

    async def evaluate(self, script: str, *args: Any) -> Any:
        if script == "document.scrollingElement.scrollHeight":
            try:
                return next(self._heights)
            except StopIteration:
                return 0
        if script == "window.scrollTo(0, 0)":
            self.scroll_calls.append(0)
            return None
        if script == "window.scrollTo(0, arguments[0])":
            value = args[0] if args else 0
            self.scroll_calls.append(int(value))
            return None
        if script == "navigator.userAgent":
            return self.user_agent
        return None

    async def wait_for_timeout(self, timeout_ms: int) -> None:  # noqa: ARG002
        return None

    async def content(self) -> str:
        return self.dom_html

    async def close(self) -> None:
        return None


class _FakeContext:
    def __init__(self, page: _FakePage) -> None:
        self._page = page

    async def new_page(self) -> _FakePage:
        return self._page


async def _stub_apply_blocklist(page, *, url: str, config: BlocklistConfig) -> dict[str, int]:  # noqa: ARG001
    await page.add_style_tag(content="/* masked */")
    return {"#banner": 2}


async def _stub_collect_warnings(page, settings: WarningSettings) -> list[CaptureWarningEntry]:  # noqa: ARG002
    return [
        CaptureWarningEntry(code="canvas-heavy", message="canvas", count=5, threshold=3),
    ]


async def _stub_tiles(image_bytes: bytes, **kwargs: Any) -> list[TileSlice]:  # noqa: ARG001
    index = kwargs.get("tile_index_offset", 0)
    y_offset = kwargs.get("viewport_y_offset", 0)
    tile = TileSlice(
        index=index,
        png_bytes=b"tile",
        sha256=f"sha{index}",
        width=100,
        height=100,
        scale=1.0,
        source_y_offset=int(y_offset),
        viewport_y_offset=int(y_offset),
        overlap_px=kwargs.get("overlap_px", 0),
        top_overlap_sha256="hash",
        bottom_overlap_sha256="hash",
    )
    return [tile]


@pytest.mark.asyncio()
async def test_perform_viewport_sweeps_handles_shrink_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _FakePage(scroll_heights=[3000, 2500, 2500, 2500, 2500])
    context = cast(Any, _FakeContext(page))
    blocklist_config = BlocklistConfig(version="test", global_selectors=(), domain_selectors={})
    warning_settings = WarningSettings(
        canvas_warning_threshold=3,
        video_warning_threshold=2,
        shrink_warning_threshold=1,
        overlap_warning_ratio=0.6,
        seam_warning_ratio=0.8,
        seam_warning_min_pairs=1,
    )
    monkeypatch.setattr(capture_module, "apply_blocklist", _stub_apply_blocklist)
    monkeypatch.setattr(capture_module, "collect_capture_warnings", _stub_collect_warnings)
    monkeypatch.setattr(capture_module, "slice_into_tiles", _stub_tiles)
    monkeypatch.setattr(capture_module, "validate_tiles", lambda tiles: None)

    tiles, stats, user_agent, blocklist_hits, warnings, dom_bytes, failures = await _perform_viewport_sweeps(
        context=cast(capture_module.BrowserContext, context),
        config=CaptureConfig(url="https://example.com"),
        viewport_overlap_px=200,
        tile_overlap_px=50,
        target_long_side_px=800,
        settle_ms=1,
        max_steps=5,
        mask_selectors=(),
        shrink_retry_limit=1,
        blocklist_config=blocklist_config,
        warning_settings=warning_settings,
    )

    assert stats.shrink_events == 1
    assert stats.retry_attempts == 1
    assert stats.sweep_count >= 2
    assert stats.overlap_pairs == stats.sweep_count - 1
    assert stats.overlap_match_ratio == pytest.approx(1.0)
    assert user_agent == "FakeAgent/1.0"
    assert blocklist_hits == {"#banner": 2}
    codes = {warning.code for warning in warnings}
    assert "canvas-heavy" in codes
    assert "scroll-shrink" in codes
    assert dom_bytes == b"<html></html>"
    assert failures == []
    assert len(tiles) == stats.sweep_count
    # Ensure scrollTo was invoked with the expected offsets (0 for reset plus >0 for sweeps).
    assert page.scroll_calls[0] == 0
    assert any(offset > 0 for offset in page.scroll_calls[1:])
