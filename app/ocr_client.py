"""olmOCR client adapters for remote/local inference."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class OCRRequest:
    """Describe each tile submission to the OCR backend."""

    tile_id: str
    tile_bytes: bytes
    model: str


async def submit_tiles(*, requests: list[OCRRequest]) -> list[str]:
    """Placeholder for asynchronous OCR dispatch."""

    raise NotImplementedError("submit_tiles must talk to the olmOCR service")
