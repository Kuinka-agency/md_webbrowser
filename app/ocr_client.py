"""olmOCR client adapters for remote/local inference."""

from __future__ import annotations

import base64
import logging
import asyncio
from dataclasses import dataclass
from typing import Sequence

import httpx

from app.settings import Settings, get_settings

LOGGER = logging.getLogger(__name__)
DEFAULT_ENDPOINT_SUFFIX = "/v1/ocr"
REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)


@dataclass(slots=True)
class OCRRequest:
    """Describe each tile submission to the OCR backend."""

    tile_id: str
    tile_bytes: bytes
    model: str | None = None


async def submit_tiles(
    *,
    requests: Sequence[OCRRequest],
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[str]:
    """Submit tiles to the configured olmOCR endpoint.

    Parameters
    ----------
    requests:
        Ordered sequence of tile payloads to submit.
    settings:
        Optional settings override; defaults to the global settings singleton.
    client:
        Optional ``httpx.AsyncClient`` (useful for tests). When omitted, a client
        is created for the duration of this call.
    """

    if not requests:
        return []

    cfg = settings or get_settings()
    server_url = cfg.ocr.server_url.rstrip("/")
    endpoint = f"{server_url}{DEFAULT_ENDPOINT_SUFFIX}"

    headers = {"Content-Type": "application/json"}
    if cfg.ocr.api_key:
        headers["Authorization"] = f"Bearer {cfg.ocr.api_key}"

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT, http2=True)

    limit = max(1, cfg.ocr.max_concurrency)
    if cfg.ocr.min_concurrency:
        limit = max(limit, cfg.ocr.min_concurrency)
    semaphore = asyncio.Semaphore(limit)
    responses: list[str | None] = [None] * len(requests)

    async def _submit(index: int, request: OCRRequest) -> None:
        async with semaphore:
            payload = _build_payload(request, cfg)
            LOGGER.debug("Submitting tile %s to olmOCR", request.tile_id)
            response = await http_client.post(endpoint, headers=headers, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # pragma: no cover - network failure
                LOGGER.exception("olmOCR request failed: status=%s", exc.response.status_code)
                raise
            data = response.json()
            responses[index] = _extract_markdown(data, request.tile_id)

    try:
        await asyncio.gather(*(_submit(idx, request) for idx, request in enumerate(requests)))
    finally:
        if owns_client:
            await http_client.aclose()

    return [chunk or "" for chunk in responses]


def _build_payload(request: OCRRequest, settings: Settings) -> dict:
    image_b64 = base64.b64encode(request.tile_bytes).decode("ascii")
    model = request.model or settings.ocr.model
    return {
        "model": model,
        "input": [
            {
                "id": request.tile_id,
                "image": image_b64,
            }
        ],
        "options": {
            "fp8": settings.ocr.use_fp8,
        },
    }


def _extract_markdown(response_json: dict, tile_id: str) -> str:
    """Normalize various olmOCR response formats."""

    if not isinstance(response_json, dict):
        raise ValueError("OCR response must be a JSON object")

    # Preferred schema: {"results": [{"markdown": "..."}]}
    results = response_json.get("results")
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict) and "markdown" in first:
            return str(first["markdown"])

    # Legacy schema: {"data": [{"content": "..."}]}
    data_entries = response_json.get("data")
    if isinstance(data_entries, list) and data_entries:
        entry = data_entries[0]
        if isinstance(entry, dict):
            if "markdown" in entry:
                return str(entry["markdown"])
            if "content" in entry:
                return str(entry["content"])

    # Single-field fallback
    if "markdown" in response_json:
        return str(response_json["markdown"])
    if "content" in response_json:
        return str(response_json["content"])

    raise ValueError(f"OCR response missing markdown content for tile {tile_id}")
