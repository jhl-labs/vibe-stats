"""CLI entrypoint for vibe-stats."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta

import click

from . import __version__


def _parse_relative_date(value: str) -> str | None:
    """Parse relative date like 7d, 2w, 3m, 1y into YYYY-MM-DD string."""
    match = re.match(r"^(\d+)([dwmy])$", value)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "d":
        delta = timedelta(days=amount)
    elif unit == "w":
        delta = timedelta(weeks=amount)
    elif unit == "m":
        delta = timedelta(days=amount * 30)
    else:  # unit == "y"
        delta = timedelta(days=amount * 365)
    target = datetime.now() - delta
    return target.strftime("%Y-%m-%d")


def _resolve_date(value: str | None) -> str | None:
    """Resolve a date value that may be relative (7d, 30d, 3m, 1y) or absolute (YYYY-MM-DD)."""
    if value is None:
        return None
    parsed = _parse_relative_date(value)
    if parsed is not None:
        return parsed
    return value


@click.command()
@click.argument("target")
@click.option(
    "--token",
    envvar="GITHUB_TOKEN",
    required=True,
    help="GitHub API token (default: $GITHUB_TOKEN)",
)
@click.option("--top-n", default=10, show_default=True, help="Number of top contributors to show")
@click.option("--since", default=None, help="Start date filter (YYYY-MM-DD or relative: 7d, 2w, 3m, 1y)")
@click.option("--until", default=None, help="End date filter (YYYY-MM-DD or relative: 7d, 2w, 3m, 1y)")
@click.option("--include-forks", is_flag=True, default=False, help="Include forked repositories")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json", "csv"], case_sensitive=False),
    default="table",
    show_default=True,
    help="Output format",
)
@click.option("--no-cache", is_flag=True, default=False, help="Disable caching")
@click.option(
    "--exclude-repo",
    multiple=True,
    help="Exclude specific repositories (can be specified multiple times)",
)
@click.option(
    "--sort-by",
    type=click.Choice(["commits", "additions", "deletions", "lines"], case_sensitive=False),
    default="commits",
    show_default=True,
    help="Sort contributors by this metric",
)
@click.option("--exclude-bots", is_flag=True, default=False, help="Exclude bot accounts from contributors")
@click.option("--min-commits", default=0, show_default=True, help="Minimum commits to include a contributor")
@click.option("--output", "output_file", default=None, type=click.Path(), help="Save output to file")
@click.version_option(version=__version__)
def main(
    target: str,
    token: str,
    top_n: int,
    since: str | None,
    until: str | None,
    include_forks: bool,
    output_format: str,
    no_cache: bool,
    exclude_repo: tuple[str, ...],
    sort_by: str,
    exclude_bots: bool,
    min_commits: int,
    output_file: str | None,
) -> None:
    """Collect and display GitHub contribution statistics.

    TARGET can be an org/user name (e.g. "myorg") or a specific repo (e.g. "myorg/myrepo").
    """
    # Parse target: org or org/repo
    if "/" in target:
        org, repo = target.split("/", 1)
    else:
        org = target
        repo = None

    # Resolve relative dates
    since = _resolve_date(since)
    until = _resolve_date(until)

    # Convert YYYY-MM-DD to ISO 8601 for GitHub API
    iso_since = f"{since}T00:00:00Z" if since else None
    iso_until = f"{until}T23:59:59Z" if until else None

    from .orchestrator import run

    asyncio.run(run(
        org=org,
        token=token,
        top_n=top_n,
        since=iso_since,
        until=iso_until,
        include_forks=include_forks,
        output_format=output_format,
        no_cache=no_cache,
        repo=repo,
        exclude_repos=list(exclude_repo),
        sort_by=sort_by,
        exclude_bots=exclude_bots,
        min_commits=min_commits,
        output_file=output_file,
    ))


if __name__ == "__main__":  # pragma: no cover
    main()
