"""Tile slicing utilities backed by pyvips."""

from __future__ import annotations

from typing import Iterable


async def slice_into_tiles(image_bytes: bytes, *, overlap_px: int = 120) -> Iterable[bytes]:
    """Placeholder that will eventually fan the bytes through pyvips tiling."""

    raise NotImplementedError("slice_into_tiles is not wired yet")
