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

_SORT_LABELS = {
    "commits": "Commits",
    "additions": "Additions",
    "deletions": "Deletions",
    "lines": "Lines",
}


def _format_number(n: int) -> str:
    return f"{n:,}"


def _make_bar(percentage: float, width: int = 20) -> str:
    filled = round(percentage / 100 * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def _write_to_file(content: str, output_file: str) -> None:
    """Write content to a file and print confirmation."""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)
    Console().print(f"Saved to {output_file}")


def render_report(
    report: OrgReport,
    top_n: int = 10,
    sort_by: str = "commits",
    output_file: str | None = None,
) -> None:
    """Render an OrgReport to the terminal using rich."""
    if output_file:
        string_io = io.StringIO()
        console = Console(file=string_io, force_terminal=False, width=120)
    else:
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
    summary.add_row("Open PRs", _format_number(report.total_open_prs))
    summary.add_row("Merged PRs", _format_number(report.total_merged_prs))
    summary.add_row("Open Issues", _format_number(report.total_open_issues))
    console.print(summary)
    console.print()

    # Repository summary table (only when multiple repos)
    if len(report.repos) > 1:
        console.print("[bold]Repository Summary[/bold]")
        repo_table = Table(show_header=True, header_style="bold")
        repo_table.add_column("Repo")
        repo_table.add_column("Commits", justify="right")
        repo_table.add_column("Additions", justify="right")
        repo_table.add_column("Deletions", justify="right")
        repo_table.add_column("Top Language")
        repo_table.add_column("Contributors", justify="right")

        sorted_repos = sorted(report.repos, key=lambda r: r.total_commits, reverse=True)
        for r in sorted_repos:
            top_lang = r.languages[0].language if r.languages else "-"
            repo_table.add_row(
                r.name,
                _format_number(r.total_commits),
                _format_number(r.total_additions),
                _format_number(r.total_deletions),
                top_lang,
                str(len(r.contributors)),
            )
        console.print(repo_table)
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

        # Add sort indicator
        sort_label = _SORT_LABELS.get(sort_by, "Commits")
        columns = ["Commits", "Additions", "Deletions"]
        for col in columns:
            label = f"{col} \u25bc" if col == sort_label else col
            contrib_table.add_column(label, justify="right")

        if sort_by == "lines":
            contrib_table.add_column("Lines \u25bc", justify="right")

        for i, c in enumerate(report.contributors[:top_n], 1):
            row = [
                str(i),
                c.username,
                _format_number(c.commits),
                _format_number(c.additions),
                _format_number(c.deletions),
            ]
            if sort_by == "lines":
                row.append(_format_number(c.additions + c.deletions))
            contrib_table.add_row(*row)
        console.print(contrib_table)
        console.print()

    if output_file:
        _write_to_file(string_io.getvalue(), output_file)


def render_json(report: OrgReport, output_file: str | None = None) -> None:
    """Render an OrgReport as JSON."""
    content = json.dumps(asdict(report), indent=2, ensure_ascii=False)
    if output_file:
        _write_to_file(content, output_file)
    else:
        print(content)


def render_csv(report: OrgReport, output_file: str | None = None) -> None:
    """Render contributor data as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["username", "commits", "additions", "deletions"])
    for c in report.contributors:
        writer.writerow([c.username, c.commits, c.additions, c.deletions])
    content = output.getvalue()
    if output_file:
        _write_to_file(content, output_file)
    else:
        print(content, end="")
