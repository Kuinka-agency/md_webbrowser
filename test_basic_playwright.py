#!/usr/bin/env python3
"""
Test basic Playwright functionality without pyvips dependency.
This verifies that the browser automation part works.
"""

import asyncio
from playwright.async_api import async_playwright
from pathlib import Path


async def test_basic_screenshot():
    """Test that we can navigate and take a screenshot."""
    print("Testing basic Playwright screenshot capability...")

    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            device_scale_factor=1,
        )
        page = await context.new_page()

        # Navigate to a simple page
        print("Navigating to example.com...")
        await page.goto("https://example.com", wait_until="networkidle")

        # Take a screenshot
        output_path = Path("test_screenshot.png")
        await page.screenshot(path=output_path, full_page=False)

        # Get page title and content length
        title = await page.title()
        content = await page.content()

        await browser.close()

        # Check results
        if output_path.exists():
            file_size = output_path.stat().st_size
            print(f"✅ Screenshot saved: {output_path} ({file_size:,} bytes)")
            print(f"   Page title: {title}")
            print(f"   HTML content length: {len(content):,} characters")
            return True
        else:
            print("❌ Screenshot not created")
            return False


async def test_viewport_sweep():
    """Test scrolling and taking multiple screenshots."""
    print("\nTesting viewport sweep (without tiling)...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            device_scale_factor=1,
        )
        page = await context.new_page()

        # Navigate to a longer page
        print("Navigating to a longer page...")
        await page.goto("https://en.wikipedia.org/wiki/Python_(programming_language)",
                       wait_until="networkidle")

        # Get initial scroll height
        scroll_height = await page.evaluate("document.documentElement.scrollHeight")
        viewport_height = 800
        print(f"   Page scroll height: {scroll_height}px")
        print(f"   Viewport height: {viewport_height}px")

        # Take screenshots at different scroll positions
        screenshots = []
        y_offset = 0
        step = 600  # Scroll 600px at a time (200px overlap)
        sweep_count = 0
        max_sweeps = 5  # Limit for testing

        while y_offset < scroll_height and sweep_count < max_sweeps:
            # Scroll to position
            await page.evaluate(f"window.scrollTo(0, {y_offset})")
            await page.wait_for_timeout(300)  # Wait for any animations

            # Take screenshot
            output_path = Path(f"sweep_{sweep_count:02d}.png")
            await page.screenshot(path=output_path, full_page=False)

            if output_path.exists():
                screenshots.append(output_path)
                print(f"   Screenshot {sweep_count}: {output_path} at y={y_offset}")

            y_offset += step
            sweep_count += 1

            if y_offset + viewport_height >= scroll_height:
                break

        await browser.close()

        print(f"✅ Created {len(screenshots)} viewport screenshots")
        return len(screenshots) > 0


async def main():
    """Run tests."""
    print("=" * 60)
    print("BASIC PLAYWRIGHT FUNCTIONALITY TEST")
    print("(Testing browser automation without pyvips)")
    print("=" * 60)

    # Test basic screenshot
    basic_ok = await test_basic_screenshot()

    # Test viewport sweep
    sweep_ok = await test_viewport_sweep()

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Basic screenshot: {'✅' if basic_ok else '❌'}")
    print(f"Viewport sweep:   {'✅' if sweep_ok else '❌'}")

    if basic_ok and sweep_ok:
        print("\n✅ Browser automation is working!")
        print("   The capture code should work once libvips is installed.")
    else:
        print("\n❌ Browser automation has issues")

    return basic_ok and sweep_ok


if __name__ == "__main__":
    success = asyncio.run(main())
    import sys
    sys.exit(0 if success else 1)