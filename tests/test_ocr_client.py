from __future__ import annotations

import base64
import json
import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.ocr_client import OCRRequest, submit_tiles


def _dummy_settings(server_url: str = "https://example.com/api", api_key: str | None = "sk-test"):
    ocr = SimpleNamespace(
        server_url=server_url,
        api_key=api_key,
        model="olmOCR-2-7B-1025-FP8",
        use_fp8=True,
        min_concurrency=1,
        max_concurrency=4,
    )
    return SimpleNamespace(ocr=ocr)


@pytest.mark.asyncio
async def test_submit_tiles_posts_base64_payload():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        body = json.loads(request.content.decode("utf-8"))
        captured["body"] = body
        return httpx.Response(200, json={"results": [{"markdown": "tile md"}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await submit_tiles(
            requests=[OCRRequest(tile_id="tile-1", tile_bytes=b"hello world")],
            settings=_dummy_settings(),
            client=client,
        )

    assert result == ["tile md"]
    assert captured["url"].endswith("/v1/ocr")
    payload = captured["body"]
    assert payload["model"] == "olmOCR-2-7B-1025-FP8"
    image = payload["input"][0]["image"]
    assert base64.b64decode(image.encode("ascii")) == b"hello world"


@pytest.mark.asyncio
async def test_submit_tiles_raises_when_markdown_missing():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - simple path
        return httpx.Response(200, json={"unexpected": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError):
            await submit_tiles(
                requests=[OCRRequest(tile_id="tile-1", tile_bytes=b"data")],
                settings=_dummy_settings(),
                client=client,
            )


@pytest.mark.asyncio
async def test_submit_tiles_respects_concurrency_limit():
    class RecordingClient:
        def __init__(self) -> None:
            self.inflight = 0
            self.max_inflight = 0

        async def post(self, url, headers=None, json=None):  # noqa: ANN001
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)
            await asyncio.sleep(0)
            self.inflight -= 1
            request = httpx.Request("POST", url)
            payload = json or {}
            identifier = payload.get("input", [{}])[0].get("id", "")
            return httpx.Response(200, json={"results": [{"markdown": identifier}]}, request=request)

        async def aclose(self) -> None:  # pragma: no cover - interface shim
            return None

    fake_client = RecordingClient()
    settings = _dummy_settings()
    settings.ocr.max_concurrency = 2

    requests = [
        OCRRequest(tile_id=f"tile-{idx}", tile_bytes=b"bytes")
        for idx in range(4)
    ]

    results = await submit_tiles(
        requests=requests,
        settings=settings,
        client=fake_client,  # type: ignore[arg-type]
    )

    assert results == [f"tile-{idx}" for idx in range(4)]
    assert fake_client.max_inflight <= 2
