"""Tests for the CLI module."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from vibe_stats.cli import _parse_relative_date, _resolve_date, main


def test_parse_relative_date_days():
    result = _parse_relative_date("7d")
    expected = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    assert result == expected


def test_parse_relative_date_weeks():
    result = _parse_relative_date("2w")
    expected = (datetime.now() - timedelta(weeks=2)).strftime("%Y-%m-%d")
    assert result == expected


def test_parse_relative_date_months():
    result = _parse_relative_date("3m")
    expected = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    assert result == expected


def test_parse_relative_date_years():
    result = _parse_relative_date("1y")
    expected = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    assert result == expected


def test_parse_relative_date_invalid():
    assert _parse_relative_date("abc") is None
    assert _parse_relative_date("10x") is None
    assert _parse_relative_date("") is None
    assert _parse_relative_date("2024-01-01") is None


def test_resolve_date_none():
    assert _resolve_date(None) is None


def test_resolve_date_relative():
    result = _resolve_date("30d")
    expected = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    assert result == expected


def test_resolve_date_absolute():
    assert _resolve_date("2024-01-15") == "2024-01-15"


@patch("vibe_stats.cli.asyncio.run")
@patch("vibe_stats.orchestrator.aggregate_org_report")
def test_main_org_target(mock_aggregate, mock_asyncio_run):
    """CLI should parse org target correctly."""
    runner = CliRunner()
    result = runner.invoke(main, ["myorg", "--token", "fake-token"])
    assert result.exit_code == 0
    # asyncio.run was called
    mock_asyncio_run.assert_called_once()


@patch("vibe_stats.cli.asyncio.run")
def test_main_repo_target(mock_asyncio_run):
    """CLI should parse org/repo target correctly."""
    runner = CliRunner()
    result = runner.invoke(main, ["myorg/myrepo", "--token", "fake-token"])
    assert result.exit_code == 0
    call_kwargs = mock_asyncio_run.call_args
    # The coroutine was passed to asyncio.run
    mock_asyncio_run.assert_called_once()


@patch("vibe_stats.cli.asyncio.run")
def test_main_with_relative_since(mock_asyncio_run):
    """CLI should resolve relative dates."""
    runner = CliRunner()
    result = runner.invoke(main, ["myorg", "--token", "fake-token", "--since", "7d"])
    assert result.exit_code == 0


@patch("vibe_stats.cli.asyncio.run")
def test_main_with_all_options(mock_asyncio_run):
    """CLI should accept all new options."""
    runner = CliRunner()
    result = runner.invoke(main, [
        "myorg", "--token", "fake-token",
        "--sort-by", "additions",
        "--exclude-bots",
        "--min-commits", "5",
        "--since", "30d",
        "--until", "2024-12-31",
        "--exclude-repo", "repo1",
        "--format", "json",
    ])
    assert result.exit_code == 0


@patch("vibe_stats.cli.asyncio.run")
def test_main_with_output_option(mock_asyncio_run):
    """CLI should accept --output option."""
    runner = CliRunner()
    result = runner.invoke(main, [
        "myorg", "--token", "fake-token",
        "--output", "/tmp/test-output.json",
    ])
    assert result.exit_code == 0


def test_main_missing_token():
    """CLI should fail without token."""
    runner = CliRunner(env={"GITHUB_TOKEN": ""})
    result = runner.invoke(main, ["myorg"], catch_exceptions=False)
    assert result.exit_code != 0


def test_main_version():
    """CLI should show version."""
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output.lower() or "." in result.output
