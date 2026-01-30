"""Orchestrator: wires together client, aggregator, and renderer."""

from __future__ import annotations

from .aggregator import aggregate_org_report
from .github.client import GitHubClient
from .renderer import render_report


async def run(org: str, token: str, top_n: int = 10) -> None:
    """Main pipeline: fetch data, aggregate, render."""
    async with GitHubClient(token=token) as client:
        report = await aggregate_org_report(client, org)
        render_report(report, top_n=top_n)
