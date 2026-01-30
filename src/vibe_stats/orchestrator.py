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
) -> None:
    """Main pipeline: fetch data, aggregate, render."""
    async with GitHubClient(token=token, no_cache=no_cache) as client:
        report = await aggregate_org_report(
            client, org, since=since, until=until, include_forks=include_forks
        )

    if output_format == "json":
        render_json(report)
    elif output_format == "csv":
        render_csv(report)
    else:
        render_report(report, top_n=top_n)
