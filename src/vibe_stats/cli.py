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
@click.version_option(version=__version__)
def main(org: str, token: str, top_n: int) -> None:
    """Collect and display GitHub Organization statistics."""
    from .orchestrator import run

    asyncio.run(run(org=org, token=token, top_n=top_n))


if __name__ == "__main__":
    main()
