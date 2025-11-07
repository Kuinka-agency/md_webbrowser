"""Playwright-based capture routines (viewport sweeps, metadata logging)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CaptureConfig:
    """Inputs that describe how we should drive Chromium."""

    url: str
    viewport_width: int = 1280
    viewport_height: int = 2000
    device_scale_factor: int = 2
    color_scheme: str = "light"


async def capture_tiles(config: CaptureConfig) -> list[bytes]:
    """Stub the viewport sweep until Playwright plumbing is implemented."""

    # This intentionally raises until the real capture stack is wired up.
    raise NotImplementedError("capture_tiles requires Playwright integration")
