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

_WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _format_number(n: int) -> str:
    return f"{n:,}"


def _format_hours(h: float | None) -> str:
    if h is None:
        return "-"
    if h < 1:
        return f"{h * 60:.0f}m"
    if h < 24:
        return f"{h:.1f}h"
    return f"{h / 24:.1f}d"


def _format_date(iso: str) -> str:
    """Format an ISO 8601 date string to YYYY-MM-DD for display."""
    return iso[:10] if len(iso) >= 10 else iso


def _make_bar(percentage: float, width: int = 20) -> str:
    filled = round(percentage / 100 * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def _make_inline_bar(count: int, max_count: int, width: int = 15) -> str:
    if max_count == 0:
        return ""
    filled = round(count / max_count * width)
    return "\u2588" * filled


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
        start = _format_date(report.period_start) if report.period_start else "..."
        end = _format_date(report.period_end) if report.period_end else "..."
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

    # Summary (extended with stars/forks/archived)
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
    if report.total_stars > 0:
        summary.add_row("Total Stars", _format_number(report.total_stars))
    if report.total_forks > 0:
        summary.add_row("Total Forks", _format_number(report.total_forks))
    if report.archived_repos > 0:
        summary.add_row("Archived Repos", _format_number(report.archived_repos))
    console.print(summary)
    console.print()

    # Repository summary table (only when multiple repos)
    if len(report.repos) > 1:
        has_stars = any(r.stars > 0 for r in report.repos)
        has_forks = any(r.forks > 0 for r in report.repos)

        console.print("[bold]Repository Summary[/bold]")
        repo_table = Table(show_header=True, header_style="bold")
        repo_table.add_column("Repo", no_wrap=True)
        repo_table.add_column("Commits", justify="right", no_wrap=True)
        repo_table.add_column("+/-", justify="right", no_wrap=True)
        if has_stars:
            repo_table.add_column("Stars", justify="right", no_wrap=True)
        if has_forks:
            repo_table.add_column("Forks", justify="right", no_wrap=True)
        repo_table.add_column("Language", no_wrap=True)
        repo_table.add_column("Contribs", justify="right", no_wrap=True)

        sorted_repos = sorted(report.repos, key=lambda r: r.total_commits, reverse=True)
        for r in sorted_repos:
            top_lang = r.languages[0].language if r.languages else "-"
            name = f"[dim]A[/dim] {r.name}" if r.is_archived else r.name
            changes = f"+{_format_number(r.total_additions)} / -{_format_number(r.total_deletions)}"
            row: list[str] = [
                name,
                _format_number(r.total_commits),
                changes,
            ]
            if has_stars:
                row.append(_format_number(r.stars))
            if has_forks:
                row.append(_format_number(r.forks))
            row.append(top_lang)
            row.append(str(len(r.contributors)))
            repo_table.add_row(*row)
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

    # Commit Patterns section
    cp = report.commit_patterns
    if cp and cp.total > 0:
        console.print("[bold]Commit Patterns[/bold]")
        cp_table = Table(show_header=True, header_style="bold")
        cp_table.add_column("Type")
        cp_table.add_column("Count", justify="right")
        cp_table.add_column("Percentage", justify="right")

        type_counts = [
            ("feat", cp.feat), ("fix", cp.fix), ("refactor", cp.refactor),
            ("docs", cp.docs), ("test", cp.test), ("chore", cp.chore),
            ("style", cp.style), ("ci", cp.ci), ("other", cp.other),
        ]
        for name, count in type_counts:
            if count > 0:
                pct = round(count / cp.total * 100, 1)
                cp_table.add_row(name, _format_number(count), f"{pct}%")
        console.print(cp_table)

        # Weekday distribution
        if cp.weekday_distribution:
            console.print()
            console.print("[bold]Commits by Day of Week[/bold]")
            wd_table = Table(show_header=True, header_style="bold")
            wd_table.add_column("Day")
            wd_table.add_column("Commits", justify="right")
            wd_table.add_column("Bar")
            max_wd = max(cp.weekday_distribution.values()) if cp.weekday_distribution else 1
            for i in range(7):
                cnt = cp.weekday_distribution.get(i, 0)
                wd_table.add_row(
                    _WEEKDAY_NAMES[i],
                    _format_number(cnt),
                    _make_inline_bar(cnt, max_wd),
                )
            console.print(wd_table)

        # Peak hours (top 3 most active hours)
        if cp.hourly_distribution:
            sorted_hours = sorted(
                cp.hourly_distribution.items(), key=lambda x: x[1], reverse=True
            )[:3]
            peak_str = ", ".join(f"{h:02d}:00 ({c})" for h, c in sorted_hours)
            console.print(f"  [dim]Peak hours:[/dim] {peak_str}")

        console.print()

    # PR Insights section
    pri = report.pr_insights
    if pri and pri.total_analyzed > 0:
        console.print("[bold]PR Insights[/bold]")
        pri_table = Table(show_header=False, box=None, padding=(0, 2))
        pri_table.add_column("label", style="dim")
        pri_table.add_column("value", style="bold")
        pri_table.add_row("Total PRs Analyzed", _format_number(pri.total_analyzed))
        pri_table.add_row("Avg Merge Time", _format_hours(pri.avg_merge_hours))
        pri_table.add_row("Median Merge Time", _format_hours(pri.median_merge_hours))
        if pri.avg_close_hours is not None:
            pri_table.add_row("Avg Close Time (unmerged)", _format_hours(pri.avg_close_hours))
        if pri.draft_count > 0:
            pri_table.add_row("Draft PRs", _format_number(pri.draft_count))
        console.print(pri_table)

        if pri.top_authors:
            console.print()
            console.print("[bold]Top PR Authors[/bold]")
            author_table = Table(show_header=True, header_style="bold")
            author_table.add_column("#", justify="right")
            author_table.add_column("Author")
            author_table.add_column("PRs", justify="right")
            sorted_authors = sorted(pri.top_authors, key=lambda x: x[1], reverse=True)
            for i, (author, count) in enumerate(sorted_authors[:top_n], 1):
                author_table.add_row(str(i), author, _format_number(count))
            console.print(author_table)
        console.print()

    # Issue Insights section
    ii = report.issue_insights
    if ii and ii.total_analyzed > 0:
        console.print("[bold]Issue Insights[/bold]")

        if ii.label_distribution:
            label_table = Table(show_header=True, header_style="bold")
            label_table.add_column("Label")
            label_table.add_column("Count", justify="right")
            sorted_labels = sorted(ii.label_distribution.items(), key=lambda x: x[1], reverse=True)
            for name, count in sorted_labels[:15]:
                label_table.add_row(name, _format_number(count))
            console.print(label_table)

        if ii.top_reporters:
            console.print()
            console.print("[bold]Top Issue Reporters[/bold]")
            reporter_table = Table(show_header=True, header_style="bold")
            reporter_table.add_column("#", justify="right")
            reporter_table.add_column("Reporter")
            reporter_table.add_column("Issues", justify="right")
            for i, (reporter, count) in enumerate(ii.top_reporters[:top_n], 1):
                reporter_table.add_row(str(i), reporter, _format_number(count))
            console.print(reporter_table)
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

    # Contributor Activity Trends
    if report.contributor_trends:
        console.print(f"[bold]Contributor Activity (top {top_n})[/bold]")
        trend_table = Table(show_header=True, header_style="bold")
        trend_table.add_column("#", justify="right")
        trend_table.add_column("Username")
        trend_table.add_column("First Active", no_wrap=True)
        trend_table.add_column("Last Active", no_wrap=True)
        trend_table.add_column("Active Wks", justify="right")
        trend_table.add_column("Span Wks", justify="right")
        trend_table.add_column("Consistency", justify="right")

        for i, t in enumerate(report.contributor_trends[:top_n], 1):
            consistency = (
                f"{t.active_weeks / t.total_weeks * 100:.0f}%"
                if t.total_weeks > 0
                else "-"
            )
            trend_table.add_row(
                str(i),
                t.username,
                t.first_active_week,
                t.last_active_week,
                str(t.active_weeks),
                str(t.total_weeks),
                consistency,
            )
        console.print(trend_table)
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
