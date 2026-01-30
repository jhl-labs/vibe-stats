"""Rich-based terminal report renderer with JSON/CSV support."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import OrgReport


def _format_number(n: int) -> str:
    return f"{n:,}"


def _make_bar(percentage: float, width: int = 20) -> str:
    filled = round(percentage / 100 * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def render_report(report: OrgReport, top_n: int = 10) -> None:
    """Render an OrgReport to the terminal using rich."""
    console = Console()

    # Header panel
    period = ""
    if report.period_start or report.period_end:
        start = report.period_start or "..."
        end = report.period_end or "..."
        period = f"\nPeriod: {start} ~ {end}"

    console.print(Panel(
        Text(f"vibe-stats: {report.org}{period}", justify="center"),
        style="bold cyan",
    ))
    console.print()

    # Failed repos warning
    if report.failed_repos:
        console.print(
            f"[bold yellow]Warning:[/bold yellow] Failed to collect stats for "
            f"{len(report.failed_repos)} repo(s): {', '.join(report.failed_repos)}"
        )
        console.print()

    # Summary
    console.print("[bold]Summary[/bold]")
    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column("label", style="dim")
    summary.add_column("value", style="bold")
    summary.add_row("Repositories", _format_number(report.total_repos))
    summary.add_row("Total Commits", _format_number(report.total_commits))
    summary.add_row("Additions", _format_number(report.total_additions))
    summary.add_row("Deletions", _format_number(report.total_deletions))
    console.print(summary)
    console.print()

    # Language distribution
    if report.languages:
        console.print("[bold]Language Distribution[/bold]")
        lang_table = Table(show_header=True, header_style="bold")
        lang_table.add_column("Language")
        lang_table.add_column("Bar")
        lang_table.add_column("Percentage", justify="right")
        lang_table.add_column("Bytes", justify="right")

        for lang in report.languages[:15]:
            lang_table.add_row(
                lang.language,
                _make_bar(lang.percentage),
                f"{lang.percentage}%",
                _format_number(lang.bytes),
            )
        console.print(lang_table)
        console.print()

    # Top contributors
    if report.contributors:
        console.print(f"[bold]Top Contributors (top {top_n})[/bold]")
        contrib_table = Table(show_header=True, header_style="bold")
        contrib_table.add_column("#", justify="right")
        contrib_table.add_column("Username")
        contrib_table.add_column("Commits", justify="right")
        contrib_table.add_column("Additions", justify="right")
        contrib_table.add_column("Deletions", justify="right")

        for i, c in enumerate(report.contributors[:top_n], 1):
            contrib_table.add_row(
                str(i),
                c.username,
                _format_number(c.commits),
                _format_number(c.additions),
                _format_number(c.deletions),
            )
        console.print(contrib_table)
        console.print()


def render_json(report: OrgReport) -> None:
    """Render an OrgReport as JSON to stdout."""
    print(json.dumps(asdict(report), indent=2, ensure_ascii=False))


def render_csv(report: OrgReport) -> None:
    """Render contributor data as CSV to stdout."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["username", "commits", "additions", "deletions"])
    for c in report.contributors:
        writer.writerow([c.username, c.commits, c.additions, c.deletions])
    print(output.getvalue(), end="")
