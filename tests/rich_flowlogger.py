from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.syntax import Syntax


LogValue = Any | tuple[Any, str | None]


def create_console() -> Console:
    """Return a deterministic console for FlowLogger-based tests."""

    return Console(record=True, width=120, color_system=None, force_terminal=False, no_color=True)


@dataclass
class FlowLogger:
    """Structured Rich logger tailored for integration/E2E tests."""

    console: Console
    flow_name: str

    def __post_init__(self) -> None:
        self._steps: list[str] = []
        self._timeline: list[tuple[str, float]] = []
        self._last_time = time.perf_counter()

    def banner(self, text: str) -> None:
        self.console.rule(f"{self.flow_name}: {text}")

    def step(
        self,
        title: str,
        *,
        description: str,
        inputs: Mapping[str, LogValue] | None = None,
        functions: Sequence[str] | None = None,
        outputs: Mapping[str, LogValue] | None = None,
        command: str | None = None,
        syntax_blocks: Sequence[tuple[str, str]] | None = None,
    ) -> None:
        sections: list[Any] = [description]
        if inputs:
            sections.append(_mapping_table("Inputs", inputs, self.flow_name))
        if functions:
            sections.append(_functions_table(functions))
        if outputs:
            sections.append(_mapping_table("Outputs", outputs, self.flow_name))
        self._record_step(title)
        self.console.print(Panel.fit(Group(*sections), title=f"Step ▸ {title}", border_style="blue"))
        if command:
            self.console.print(Panel.fit(command, title=f"Command ▸ {title}", border_style="magenta"))
        if syntax_blocks:
            for language, snippet in syntax_blocks:
                syntax = Syntax(snippet, language, theme="ansi_dark")
                self.console.print(Panel.fit(syntax, title=f"Context ▸ {title}", border_style="cyan"))

    def finish(self, summary: Mapping[str, LogValue]) -> None:
        self._render_progress()
        self.console.print(
            Panel.fit(
                _mapping_table("Summary", summary, self.flow_name),
                title=f"Summary ▸ {self.flow_name}",
                border_style="green",
            )
        )

    def _record_step(self, title: str) -> None:
        now = time.perf_counter()
        delta_ms = (now - self._last_time) * 1000
        self._last_time = now
        self._steps.append(title)
        self._timeline.append((title, delta_ms))

    def _render_progress(self) -> None:
        total = max(len(self._steps), 1)
        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=self.console,
            transient=False,
        )
        with progress:
            task_id = progress.add_task("Flow progress", total=total)
            for _ in self._steps or ["init"]:
                progress.advance(task_id)
        timing = Table("Step", "Δms", title="Timing", box=None)
        for title, delta in self._timeline:
            timing.add_row(title, f"{delta:.2f}")
        if not self._timeline:
            timing.add_row("init", "0.00")
        self.console.print(Panel.fit(timing, border_style="yellow", title="Timing Snapshot"))


def _mapping_table(title: str, mapping: Mapping[str, LogValue], default_source: str) -> Table:
    table = Table("Field", "Value", "Source", title=title, box=None, expand=True)
    for key, raw_value in mapping.items():
        value, source = _normalize_entry(raw_value, default_source)
        table.add_row(str(key), value, source or default_source)
    return table


def _normalize_entry(value: LogValue, default_source: str) -> tuple[str, str]:
    if isinstance(value, tuple) and len(value) == 2:
        raw_value, source = value
        return str(raw_value), str(source) if source else default_source
    return str(value), default_source


def _functions_table(functions: Sequence[str]) -> Table:
    table = Table("Order", "Function", "Source", title="Functions", box=None)
    for idx, name in enumerate(functions, start=1):
        table.add_row(str(idx), name, "FlowLogger")
    return table
