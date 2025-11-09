#!/usr/bin/env python3
"""
Advanced Integration Test Suite with Live Monitoring and Pipeline Tracing
Tests the complete Markdown Web Browser pipeline with extreme detail
"""

from __future__ import annotations

import asyncio
import hashlib
import httpx
import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    MofNCompleteColumn,
)
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree
from rich.text import Text
from rich.columns import Columns
from rich.rule import Rule
from rich import box
from rich.layout import Layout
from rich.align import Align
from rich.markdown import Markdown
from rich.traceback import Traceback

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.settings import get_settings


class TestStage(Enum):
    """Test pipeline stages."""
    INIT = "Initializing"
    BROWSER_START = "Starting Browser"
    CAPTURE = "Capturing Page"
    TILING = "Tiling Images"
    OCR = "Running OCR"
    STITCHING = "Stitching Markdown"
    VALIDATION = "Validating Output"
    COMPLETE = "Complete"
    FAILED = "Failed"


@dataclass
class PipelineEvent:
    """Represents an event in the pipeline."""
    timestamp: float
    stage: TestStage
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    level: str = "info"  # info, warning, error, success


@dataclass
class TestCase:
    """Represents a test case."""
    name: str
    url: str
    description: str
    expected_tiles: Optional[int] = None
    expected_links: Optional[int] = None
    timeout: float = 60.0
    tags: List[str] = field(default_factory=list)


class PipelineMonitor:
    """Monitors and displays the capture pipeline in detail."""

    def __init__(self, console: Console):
        self.console = console
        self.events: List[PipelineEvent] = []
        self.metrics: Dict[str, Any] = {}
        self.start_time = time.time()

    def add_event(self, stage: TestStage, message: str, data: Dict[str, Any] = None, level: str = "info"):
        """Add an event to the pipeline."""
        event = PipelineEvent(
            timestamp=time.time(),
            stage=stage,
            message=message,
            data=data or {},
            level=level
        )
        self.events.append(event)

    def get_timeline_table(self) -> Table:
        """Create a timeline table of events."""
        table = Table(title="Pipeline Timeline", box=box.ROUNDED)
        table.add_column("Time", style="dim", width=12)
        table.add_column("Stage", style="cyan", width=20)
        table.add_column("Event", style="white")
        table.add_column("Details", style="dim")

        for event in self.events[-10:]:  # Show last 10 events
            time_str = datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S.%f")[:-3]

            # Color code by level
            if event.level == "error":
                stage_style = "red"
            elif event.level == "warning":
                stage_style = "yellow"
            elif event.level == "success":
                stage_style = "green"
            else:
                stage_style = "cyan"

            details = ", ".join(f"{k}={v}" for k, v in event.data.items()[:3])

            table.add_row(
                time_str,
                f"[{stage_style}]{event.stage.value}[/{stage_style}]",
                event.message,
                details[:40] + "..." if len(details) > 40 else details
            )

        return table

    def get_metrics_panel(self) -> Panel:
        """Create a metrics panel."""
        elapsed = time.time() - self.start_time

        metrics_text = Group(
            Text(f"Elapsed Time: {elapsed:.2f}s", style="cyan"),
            Text(f"Events: {len(self.events)}", style="yellow"),
            Text(f"Current Stage: {self.events[-1].stage.value if self.events else 'N/A'}", style="green"),
        )

        if self.metrics:
            metrics_table = Table(box=None)
            metrics_table.add_column("Metric", style="cyan")
            metrics_table.add_column("Value", style="yellow")

            for key, value in self.metrics.items():
                metrics_table.add_row(key, str(value))

            metrics_text = Group(metrics_text, Rule(style="dim"), metrics_table)

        return Panel(metrics_text, title="📊 Metrics", border_style="blue")


class AdvancedIntegrationTester:
    """Advanced integration test runner with live monitoring."""

    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url
        self.console = Console(width=160, record=True)
        self.settings = get_settings()
        self.test_cases: List[TestCase] = []
        self.results: List[Dict[str, Any]] = []

    def setup_test_cases(self):
        """Setup test cases."""
        self.test_cases = [
            TestCase(
                name="Simple HTML Page",
                url="https://example.com",
                description="Basic HTML page with minimal content",
                expected_tiles=1,
                expected_links=1,
                tags=["basic", "fast"]
            ),
            TestCase(
                name="Wikipedia Article",
                url="https://en.wikipedia.org/wiki/Python_(programming_language)",
                description="Complex page with images, tables, and many links",
                expected_tiles=5,
                expected_links=50,
                timeout=120.0,
                tags=["complex", "slow"]
            ),
            TestCase(
                name="GitHub Repository",
                url="https://github.com/anthropics/anthropic-sdk-python",
                description="Dynamic SPA with code highlighting",
                expected_tiles=3,
                tags=["spa", "dynamic"]
            ),
        ]

    async def monitor_job_with_events(self, job_id: str, monitor: PipelineMonitor) -> Dict[str, Any]:
        """Monitor a job and track pipeline events."""

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            poll_count = 0
            max_polls = 120
            last_state = None

            while poll_count < max_polls:
                poll_count += 1
                await asyncio.sleep(0.5)

                try:
                    response = await client.get(f"{self.api_url}/jobs/{job_id}")
                    if response.status_code != 200:
                        monitor.add_event(
                            TestStage.FAILED,
                            f"Failed to get job status: {response.status_code}",
                            level="error"
                        )
                        return {"success": False, "error": f"Status code: {response.status_code}"}

                    job_data = response.json()
                    state = job_data.get("state", "UNKNOWN")

                    # Track state changes
                    if state != last_state:
                        last_state = state

                        # Map states to stages and add events
                        if state == "BROWSER_STARTING":
                            monitor.add_event(TestStage.BROWSER_START, "Launching Playwright browser")
                        elif state == "BROWSER_READY":
                            monitor.add_event(TestStage.BROWSER_START, "Browser ready", level="success")
                        elif state == "CAPTURE_RUNNING":
                            monitor.add_event(TestStage.CAPTURE, "Performing viewport sweeps")
                            progress = job_data.get("progress", {})
                            if progress:
                                monitor.metrics["tiles_captured"] = progress.get("done", 0)
                        elif state == "CAPTURE_DONE":
                            monitor.add_event(TestStage.CAPTURE, "Capture complete", level="success")
                            manifest = job_data.get("manifest", {})
                            if manifest.get("tiles_total"):
                                monitor.add_event(
                                    TestStage.TILING,
                                    f"Generated {manifest['tiles_total']} tiles",
                                    {"tiles": manifest["tiles_total"]},
                                    level="success"
                                )
                        elif state == "OCR_RUNNING":
                            monitor.add_event(TestStage.OCR, "Processing tiles with OCR")
                            progress = job_data.get("progress", {})
                            if progress:
                                monitor.metrics["ocr_progress"] = f"{progress.get('done', 0)}/{progress.get('total', 0)}"
                        elif state == "DONE":
                            monitor.add_event(TestStage.COMPLETE, "Job completed successfully", level="success")
                            return {"success": True, "data": job_data}
                        elif state == "FAILED":
                            error = job_data.get("error", "Unknown error")
                            monitor.add_event(TestStage.FAILED, f"Job failed: {error}", level="error")
                            return {"success": False, "error": error}

                    # Update metrics from manifest
                    manifest = job_data.get("manifest", {})
                    if manifest:
                        if manifest.get("timings"):
                            for key, value in manifest["timings"].items():
                                if value:
                                    monitor.metrics[f"time_{key}"] = f"{value}ms"

                except Exception as e:
                    monitor.add_event(
                        TestStage.FAILED,
                        f"Error polling job: {str(e)}",
                        level="error"
                    )
                    return {"success": False, "error": str(e)}

            monitor.add_event(TestStage.FAILED, "Job timed out", level="error")
            return {"success": False, "error": "Timeout"}

    async def run_test_case(self, test_case: TestCase) -> Dict[str, Any]:
        """Run a single test case with detailed monitoring."""

        monitor = PipelineMonitor(self.console)
        result = {
            "test_case": test_case.name,
            "success": False,
            "data": {}
        }

        try:
            # Initialize test
            monitor.add_event(
                TestStage.INIT,
                f"Starting test: {test_case.name}",
                {"url": test_case.url}
            )

            # Submit job
            async with httpx.AsyncClient() as client:
                monitor.add_event(TestStage.INIT, "Submitting capture job")

                response = await client.post(
                    f"{self.api_url}/jobs",
                    json={"url": test_case.url, "reuse_cache": False}
                )

                if response.status_code not in [200, 202]:
                    raise Exception(f"Failed to submit job: {response.status_code}")

                job_data = response.json()
                job_id = job_data["id"]

                monitor.add_event(
                    TestStage.INIT,
                    f"Job submitted",
                    {"job_id": job_id},
                    level="success"
                )

            # Monitor job with live display
            layout = self.create_monitoring_layout(test_case, monitor)

            with Live(layout, refresh_per_second=2, console=self.console) as live:
                job_result = await self.monitor_job_with_events(job_id, monitor)

                # Validate results
                if job_result["success"]:
                    monitor.add_event(TestStage.VALIDATION, "Validating results")

                    validation_results = await self.validate_results(
                        job_id,
                        test_case,
                        job_result["data"],
                        monitor
                    )

                    result["success"] = validation_results["success"]
                    result["data"] = {
                        "job_id": job_id,
                        "validation": validation_results,
                        "metrics": monitor.metrics
                    }
                else:
                    result["data"]["error"] = job_result.get("error", "Unknown error")

        except Exception as e:
            monitor.add_event(
                TestStage.FAILED,
                f"Test failed with exception: {str(e)}",
                level="error"
            )
            result["data"]["error"] = str(e)
            result["data"]["traceback"] = traceback.format_exc()

        return result

    async def validate_results(
        self,
        job_id: str,
        test_case: TestCase,
        job_data: Dict[str, Any],
        monitor: PipelineMonitor
    ) -> Dict[str, Any]:
        """Validate job results against expectations."""

        validation = {"success": True, "checks": {}}

        try:
            async with httpx.AsyncClient() as client:
                # Check manifest
                manifest = job_data.get("manifest", {})

                if test_case.expected_tiles and manifest.get("tiles_total"):
                    actual_tiles = manifest["tiles_total"]
                    expected_tiles = test_case.expected_tiles
                    tiles_match = abs(actual_tiles - expected_tiles) <= 2  # Allow some variance

                    validation["checks"]["tiles"] = {
                        "expected": expected_tiles,
                        "actual": actual_tiles,
                        "passed": tiles_match
                    }

                    if tiles_match:
                        monitor.add_event(
                            TestStage.VALIDATION,
                            f"Tile count validated: {actual_tiles}",
                            level="success"
                        )
                    else:
                        monitor.add_event(
                            TestStage.VALIDATION,
                            f"Tile count mismatch: expected {expected_tiles}, got {actual_tiles}",
                            level="warning"
                        )
                        validation["success"] = False

                # Check artifacts exist
                artifacts = ["out.md", "links.json", "manifest.json"]
                for artifact in artifacts:
                    response = await client.get(f"{self.api_url}/jobs/{job_id}/{artifact}")
                    exists = response.status_code == 200

                    validation["checks"][artifact] = {
                        "exists": exists,
                        "size": len(response.content) if exists else 0
                    }

                    if exists:
                        monitor.add_event(
                            TestStage.VALIDATION,
                            f"Artifact {artifact} verified",
                            {"size": len(response.content)},
                            level="success"
                        )
                    else:
                        monitor.add_event(
                            TestStage.VALIDATION,
                            f"Artifact {artifact} missing",
                            level="error"
                        )
                        validation["success"] = False

        except Exception as e:
            monitor.add_event(
                TestStage.VALIDATION,
                f"Validation error: {str(e)}",
                level="error"
            )
            validation["success"] = False
            validation["error"] = str(e)

        return validation

    def create_monitoring_layout(self, test_case: TestCase, monitor: PipelineMonitor) -> Layout:
        """Create a rich layout for live monitoring."""

        layout = Layout()

        # Header
        header = Panel(
            Align.center(
                Text(f"🧪 Testing: {test_case.name}", style="bold cyan")
            ),
            border_style="blue"
        )

        # Test info
        info_table = Table(box=None)
        info_table.add_column("Property", style="cyan")
        info_table.add_column("Value", style="yellow")
        info_table.add_row("URL", test_case.url[:50] + "..." if len(test_case.url) > 50 else test_case.url)
        info_table.add_row("Description", test_case.description)
        info_table.add_row("Tags", ", ".join(test_case.tags))
        info_table.add_row("Timeout", f"{test_case.timeout}s")

        info_panel = Panel(info_table, title="📋 Test Case", border_style="cyan")

        # Create layout structure
        layout.split_column(
            Layout(header, size=3),
            Layout(name="main"),
            Layout(name="footer", size=12)
        )

        layout["main"].split_row(
            Layout(info_panel, name="info"),
            Layout(monitor.get_timeline_table(), name="timeline")
        )

        layout["footer"].update(monitor.get_metrics_panel())

        return layout

    async def run_all_tests(self):
        """Run all test cases with detailed reporting."""

        self.setup_test_cases()

        # Print header
        header = """
╔════════════════════════════════════════════════════════════════════════════════════════╗
║                    ADVANCED INTEGRATION TEST SUITE                                    ║
║                  Complete Pipeline Testing with Live Monitoring                       ║
╚════════════════════════════════════════════════════════════════════════════════════════╝
        """
        self.console.print(header, style="bold magenta")

        # System info
        info_grid = Table.grid(padding=1)
        info_grid.add_column(style="cyan", justify="right")
        info_grid.add_column(style="yellow")
        info_grid.add_column(style="cyan", justify="right")
        info_grid.add_column(style="yellow")

        info_grid.add_row("API URL:", self.api_url, "Test Cases:", str(len(self.test_cases)))
        info_grid.add_row("OCR Server:", self.settings.OLMOCR_SERVER[:40], "Timestamp:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        self.console.print(Panel(info_grid, title="Configuration", border_style="blue"))
        self.console.print()

        # Run tests
        for i, test_case in enumerate(self.test_cases, 1):
            self.console.rule(f"[cyan]Test {i}/{len(self.test_cases)}: {test_case.name}[/cyan]")

            result = await self.run_test_case(test_case)
            self.results.append(result)

            # Show result summary
            if result["success"]:
                self.console.print(f"✅ [green]Test passed: {test_case.name}[/green]")
            else:
                self.console.print(f"❌ [red]Test failed: {test_case.name}[/red]")
                if "error" in result["data"]:
                    self.console.print(f"   Error: {result['data']['error']}", style="red dim")

            self.console.print()

        # Print final summary
        self.print_final_summary()

    def print_final_summary(self):
        """Print comprehensive test summary."""

        self.console.rule("[bold magenta]Final Summary", style="magenta")

        # Results table
        results_table = Table(title="Test Results", box=box.DOUBLE_EDGE)
        results_table.add_column("Test Case", style="cyan")
        results_table.add_column("Result", style="bold")
        results_table.add_column("Job ID", style="dim")
        results_table.add_column("Validation", style="yellow")

        passed = 0
        failed = 0

        for result in self.results:
            success = result["success"]
            if success:
                passed += 1
                status = "[green]✅ PASS[/green]"
            else:
                failed += 1
                status = "[red]❌ FAIL[/red]"

            job_id = result["data"].get("job_id", "N/A")[:8] + "..." if result["data"].get("job_id") else "N/A"

            validation = result["data"].get("validation", {})
            val_summary = f"{sum(1 for c in validation.get('checks', {}).values() if c.get('passed'))}/{len(validation.get('checks', {}))}" if validation.get('checks') else "N/A"

            results_table.add_row(
                result["test_case"],
                status,
                job_id,
                val_summary
            )

        self.console.print(results_table)

        # Statistics
        total = len(self.results)
        success_rate = (passed / total * 100) if total > 0 else 0

        stats_panel = Panel(
            Align.center(
                Group(
                    Text(f"Total Tests: {total}", style="cyan"),
                    Text(f"Passed: {passed}", style="green"),
                    Text(f"Failed: {failed}", style="red" if failed > 0 else "dim"),
                    Text(f"Success Rate: {success_rate:.1f}%", style="green" if success_rate >= 80 else "yellow" if success_rate >= 60 else "red"),
                )
            ),
            title="📊 Statistics",
            border_style="magenta"
        )

        self.console.print(stats_panel)

        # Save report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = Path(f"integration_test_advanced_{timestamp}.html")
        report_path.write_text(self.console.export_html(clear=False), encoding="utf-8")

        self.console.print(f"\n📄 Report saved to: {report_path}")

        # Final verdict
        if success_rate == 100:
            verdict = "🎉 PERFECT! All tests passed!"
            style = "bold green"
        elif success_rate >= 80:
            verdict = "✅ GOOD! Most tests passed"
            style = "bold yellow"
        else:
            verdict = "❌ NEEDS ATTENTION! Many tests failed"
            style = "bold red"

        self.console.print(Panel(
            Align.center(Text(verdict, style=style)),
            border_style=style.split()[1],
            box=box.DOUBLE
        ))


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Advanced Integration Testing")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API URL")

    args = parser.parse_args()

    tester = AdvancedIntegrationTester(api_url=args.api_url)
    await tester.run_all_tests()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted")
        sys.exit(1)