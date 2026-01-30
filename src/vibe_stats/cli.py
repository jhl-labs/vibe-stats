"""CLI entrypoint for vibe-stats."""

from __future__ import annotations

import asyncio

import click

from . import __version__


@click.command()
@click.argument("org")
@click.option(
    "--token",
    envvar="GITHUB_TOKEN",
    required=True,
    help="GitHub API token (default: $GITHUB_TOKEN)",
)
@click.option("--top-n", default=10, show_default=True, help="Number of top contributors to show")
@click.option("--since", default=None, help="Start date filter (YYYY-MM-DD)")
@click.option("--until", default=None, help="End date filter (YYYY-MM-DD)")
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
@click.version_option(version=__version__)
def main(
    org: str,
    token: str,
    top_n: int,
    since: str | None,
    until: str | None,
    include_forks: bool,
    output_format: str,
    no_cache: bool,
) -> None:
    """Collect and display GitHub Organization statistics."""
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
    ))


if __name__ == "__main__":
    main()
