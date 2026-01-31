"""Orchestrator: wires together client, aggregator, and renderer."""

from __future__ import annotations

from .aggregator import aggregate_org_report
from .github.client import GitHubClient
from .renderer import render_csv, render_json, render_report


async def run(
    org: str,
    token: str,
    top_n: int = 10,
    since: str | None = None,
    until: str | None = None,
    include_forks: bool = False,
    output_format: str = "table",
    no_cache: bool = False,
    repo: str | None = None,
    exclude_repos: list[str] | None = None,
    sort_by: str = "commits",
    exclude_bots: bool = False,
    min_commits: int = 0,
    output_file: str | None = None,
) -> None:
    """Main pipeline: fetch data, aggregate, render."""
    async with GitHubClient(token=token, no_cache=no_cache) as client:
        report = await aggregate_org_report(
            client, org, since=since, until=until, include_forks=include_forks,
            repo=repo, exclude_repos=exclude_repos,
            sort_by=sort_by, exclude_bots=exclude_bots, min_commits=min_commits,
        )

    if output_format == "json":
        render_json(report, output_file=output_file)
    elif output_format == "csv":
        render_csv(report, output_file=output_file)
    else:
        render_report(report, top_n=top_n, sort_by=sort_by, output_file=output_file)
