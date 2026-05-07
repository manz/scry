"""Terminal rendering helpers — keep CLI commands free of formatting clutter."""

from __future__ import annotations

from collections.abc import Iterable

from rich.console import Console
from rich.table import Table

from scry.backends.base import DuplicationBlock, Issue, Measure

_SEVERITY_STYLE = {
    "BLOCKER": "bold red",
    "CRITICAL": "red",
    "MAJOR": "yellow",
    "MINOR": "blue",
    "INFO": "dim",
}

console = Console()


def render_issues(issues: Iterable[Issue]) -> int:
    """Print issues as a table. Returns the number of issues rendered."""
    table = Table(show_header=True, header_style="bold")
    for col in ("severity", "rule", "location", "message"):
        table.add_column(col)
    count = 0
    for issue in issues:
        location = f"{issue.component}:{issue.line}" if issue.line else issue.component
        table.add_row(
            f"[{_SEVERITY_STYLE.get(issue.severity, 'white')}]{issue.severity}[/]",
            issue.rule,
            location,
            issue.message,
        )
        count += 1
    if count == 0:
        console.print("[green]no open issues[/]")
        return 0
    console.print(table)
    console.print(f"[dim]{count} open issue(s)[/]")
    return count


def render_duplications(blocks: Iterable[list[DuplicationBlock]]) -> int:
    """Print duplications as `path:line+size  ↔  path:line+size  …` rows."""
    count = 0
    for dup in blocks:
        rendering = "  ↔  ".join(f"{b.component}:{b.start_line}+{b.size}" for b in dup)
        console.print(rendering)
        count += 1
    if count == 0:
        console.print("[green]no duplications[/]")
        return 0
    console.print(f"[dim]{count} duplication block(s)[/]")
    return count


def render_measures(measures: list[Measure]) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("metric")
    table.add_column("value", justify="right")
    for m in measures:
        table.add_row(m.metric, m.value or "—")
    console.print(table)
