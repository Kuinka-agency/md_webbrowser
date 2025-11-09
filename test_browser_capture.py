#!/usr/bin/env python3
"""
Test script to verify browser capture functionality.
This tests whether the core browser automation works.
"""

import asyncio
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.capture import CaptureConfig, capture_tiles
from app.settings import get_settings


async def test_basic_capture():
    """Test basic browser capture with a simple URL."""
    print("Testing browser capture functionality...")

    # Create a simple capture config
    config = CaptureConfig(
        url="https://example.com",
        viewport_width=1280,
        viewport_height=800,  # Smaller for testing
        device_scale_factor=1,  # Simpler for testing
    )

    try:
        print(f"Attempting to capture: {config.url}")
        print(f"Viewport: {config.viewport_width}x{config.viewport_height}")

        # Run the capture
        result = await capture_tiles(config)

        print(f"✅ Capture successful!")
        print(f"   - Tiles captured: {len(result.tiles)}")
        print(f"   - User agent: {result.manifest.user_agent[:50]}...")
        print(f"   - Capture time: {result.manifest.capture_ms}ms")
        print(f"   - Total scroll height: {result.manifest.sweep_stats.total_scroll_height}px")
        print(f"   - Sweep count: {result.manifest.sweep_stats.sweep_count}")

        if result.tiles:
            first_tile = result.tiles[0]
            print(f"   - First tile: {first_tile.width}x{first_tile.height}px")
            print(f"   - Tile data size: {len(first_tile.png_bytes)} bytes")

        if result.dom_snapshot:
            print(f"   - DOM snapshot size: {len(result.dom_snapshot)} bytes")

        # Check for warnings
        if result.manifest.warnings:
            print(f"   - Warnings: {len(result.manifest.warnings)}")
            for warning in result.manifest.warnings:
                print(f"     - {warning.code}: {warning.message}")

        return True

    except Exception as e:
        print(f"❌ Capture failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_pyvips_available():
    """Test if pyvips is available for image processing."""
    print("\nTesting pyvips availability...")

    try:
        import pyvips
        print(f"✅ pyvips is installed (version: {pyvips.version(0)}.{pyvips.version(1)}.{pyvips.version(2)})")
        return True
    except (ImportError, OSError) as e:
        print(f"❌ pyvips not available: {e}")
        print("   Install with: sudo apt-get install libvips-dev && pip install pyvips")
        return False


async def test_playwright_installed():
    """Test if Playwright browsers are installed."""
    print("\nTesting Playwright installation...")

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            # Try to launch browser
            browser = await p.chromium.launch(headless=True)
            version = browser.version
            await browser.close()
            print(f"✅ Playwright Chromium is installed (version: {version})")
            return True

    except Exception as e:
        print(f"❌ Playwright not properly installed: {e}")
        print("   Install with: playwright install chromium")
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("BROWSER CAPTURE FUNCTIONALITY TEST")
    print("=" * 60)

    # Check dependencies first
    playwright_ok = await test_playwright_installed()

    # Test pyvips separately to avoid import error
    pyvips_ok = False
    try:
        pyvips_ok = await test_pyvips_available()
    except Exception as e:
        print(f"\n❌ pyvips test failed: {e}")
        print("   This means image tiling won't work, but browser capture might still function")

    if not playwright_ok:
        print("\n⚠️  Cannot test capture without Playwright installed")
        return False

    if not pyvips_ok:
        print("\n⚠️  Warning: pyvips not available, tiling will fail")
        print("   But we can still test the browser automation part")

    # Test actual capture
    print("\n" + "-" * 60)
    capture_ok = await test_basic_capture()

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Playwright: {'✅' if playwright_ok else '❌'}")
    print(f"pyvips:     {'✅' if pyvips_ok else '❌'}")
    print(f"Capture:    {'✅' if capture_ok else '❌'}")

    all_ok = playwright_ok and capture_ok  # pyvips is optional for basic test
    print(f"\nOverall:    {'✅ PASSED' if all_ok else '❌ FAILED'}")

    return all_ok


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)