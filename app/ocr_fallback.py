"""OCR fallback and mock support for development/testing."""

from __future__ import annotations

import logging
import hashlib
from typing import Sequence

from app.ocr_client import OCRRequest, RemoteOCRClient

LOGGER = logging.getLogger(__name__)


class FallbackOCRClient:
    """OCR client with fallback to mock responses for development."""

    def __init__(self, primary_client: RemoteOCRClient, enable_mock: bool = False):
        self.primary_client = primary_client
        self.enable_mock = enable_mock

    async def submit_batch(
        self,
        tiles: Sequence[OCRRequest],
        autotune_concurrency: int | None = None
    ) -> tuple[list[str], dict]:
        """Submit batch with fallback to mock if primary fails."""

        try:
            # Try primary OCR service first
            return await self.primary_client.submit_batch(tiles, autotune_concurrency)

        except Exception as e:
            if not self.enable_mock:
                raise

            LOGGER.warning(f"Primary OCR failed: {e}, falling back to mock responses")
            return await self._generate_mock_responses(tiles)

    async def _generate_mock_responses(self, tiles: Sequence[OCRRequest]) -> tuple[list[str], dict]:
        """Generate mock OCR responses for testing."""

        responses = []
        for tile in tiles:
            # Generate deterministic content based on tile hash
            tile_hash = hashlib.sha256(tile.tile_bytes).hexdigest()[:8]

            mock_text = f"""# Example Page Content

This is mock OCR output for testing purposes.
The actual OCR service is currently unavailable.

**Tile ID:** {tile.tile_id}
**Hash:** {tile_hash}

Lorem ipsum dolor sit amet, consectetur adipiscing elit.
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.

[Learn more about this example](https://example.com)

---
*Mock OCR response generated for development/testing*"""

            responses.append(mock_text)

        telemetry = {
            "source": "mock",
            "tile_count": len(tiles),
            "status": "fallback",
        }

        return responses, telemetry


class LocalOCRFallback:
    """Fallback to local OCR processing when available."""

    def __init__(self, local_endpoint: str | None = None):
        self.local_endpoint = local_endpoint or "http://localhost:8001"
        self.available = False
        self._check_availability()

    def _check_availability(self):
        """Check if local OCR service is available."""
        import httpx
        try:
            response = httpx.get(f"{self.local_endpoint}/health", timeout=2.0)
            self.available = response.status_code == 200
            if self.available:
                LOGGER.info(f"Local OCR service available at {self.local_endpoint}")
        except:
            self.available = False
            LOGGER.debug(f"Local OCR service not available at {self.local_endpoint}")

    async def process(self, tiles: Sequence[OCRRequest]) -> tuple[list[str], dict]:
        """Process tiles using local OCR if available."""

        if not self.available:
            raise RuntimeError("Local OCR service not available")

        import httpx
        import base64
        import json

        async with httpx.AsyncClient() as client:
            # Prepare batch request
            images = [base64.b64encode(tile.tile_bytes).decode() for tile in tiles]

            response = await client.post(
                f"{self.local_endpoint}/v1/completions",
                json={
                    "images": images,
                    "model": tiles[0].model if tiles else "mock-ocr",
                    "temperature": 0.0,
                    "max_new_tokens": 2048,
                },
                timeout=30.0,
            )

            response.raise_for_status()
            data = response.json()

            # Extract text from responses
            texts = []
            for choice in data.get("choices", []):
                content = choice.get("message", {}).get("content", "")
                texts.append(content)

            return texts, {"source": "local", "endpoint": self.local_endpoint}