#!/usr/bin/env python3
"""Test the full browser capture pipeline now that libvips is installed."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.capture import capture_tiles, CaptureConfig


async def test_full_capture():
    """Test capturing a website using the actual implementation."""

    print("Testing full browser capture with libvips...")

    # Create a simple test config
    config = CaptureConfig(
        url="https://example.com",
        profile_id="test_profile",
        output_dir=Path(".cache/test_capture"),
        browser="chromium",
        wait_for="networkidle",
        timeout_ms=30000,
        scroll_delay_ms=350,
        capture_method="deterministic",
        mask_selectors=[],
        blocklist_selectors=[],
        extra_headers={},
        user_agent=None,
        viewport_width=1280,
        viewport_height=2000,
        device_scale_factor=2.0,
        color_scheme="light",
        lang="en-US",
        timezone="America/New_York"
    )

    # Ensure output directory exists
    config.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        print(f"Capturing {config.url}...")
        result = await capture_tiles(config)

        print(f"\n✅ Capture successful!")
        print(f"Tiles generated: {len(result.tiles)}")
        print(f"User agent: {result.user_agent}")
        print(f"DOM snapshot size: {len(result.dom_snapshot) if result.dom_snapshot else 0} bytes")
        print(f"Warnings: {len(result.warnings)}")
        print(f"Capture stats: {result.stats}")

        # List the generated tiles
        if result.tiles:
            print("\nGenerated tiles:")
            for i, tile in enumerate(result.tiles[:5]):  # Show first 5
                print(f"  Tile {i}: {tile.width}x{tile.height}, hash: {tile.sha256[:8]}...")

        return True

    except Exception as e:
        print(f"\n❌ Capture failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_full_capture())
    sys.exit(0 if success else 1)