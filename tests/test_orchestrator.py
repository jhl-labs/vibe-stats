"""Tests for the orchestrator module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from vibe_stats.models import ContributorStats, LanguageStats, OrgReport
from vibe_stats.orchestrator import run


def _make_report(**kwargs) -> OrgReport:
    defaults = dict(
        org="test-org",
        period_start=None,
        period_end=None,
        total_repos=1,
        total_commits=10,
        total_additions=100,
        total_deletions=50,
        total_open_prs=2,
        total_merged_prs=3,
        total_open_issues=1,
        languages=[LanguageStats(language="Python", bytes=1000, percentage=100.0)],
        contributors=[
            ContributorStats(username="alice", commits=7, additions=70, deletions=30),
        ],
        repos=[],
        failed_repos=[],
    )
    defaults.update(kwargs)
    return OrgReport(**defaults)


@pytest.mark.asyncio
@patch("vibe_stats.orchestrator.render_report")
@patch("vibe_stats.orchestrator.aggregate_org_report")
@patch("vibe_stats.orchestrator.GitHubClient")
async def test_run_table_format(mock_client_cls, mock_aggregate, mock_render):
    """run() should call render_report for table format."""
    mock_client = AsyncMock()
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    report = _make_report()
    mock_aggregate.return_value = report

    await run(org="test-org", token="fake", output_format="table")

    mock_aggregate.assert_called_once()
    mock_render.assert_called_once_with(report, top_n=10, sort_by="commits", output_file=None)


@pytest.mark.asyncio
@patch("vibe_stats.orchestrator.render_json")
@patch("vibe_stats.orchestrator.aggregate_org_report")
@patch("vibe_stats.orchestrator.GitHubClient")
async def test_run_json_format(mock_client_cls, mock_aggregate, mock_render_json):
    """run() should call render_json for json format."""
    mock_client = AsyncMock()
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_aggregate.return_value = _make_report()

    await run(org="test-org", token="fake", output_format="json")

    mock_render_json.assert_called_once()


@pytest.mark.asyncio
@patch("vibe_stats.orchestrator.render_csv")
@patch("vibe_stats.orchestrator.aggregate_org_report")
@patch("vibe_stats.orchestrator.GitHubClient")
async def test_run_csv_format(mock_client_cls, mock_aggregate, mock_render_csv):
    """run() should call render_csv for csv format."""
    mock_client = AsyncMock()
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_aggregate.return_value = _make_report()

    await run(org="test-org", token="fake", output_format="csv")

    mock_render_csv.assert_called_once()


@pytest.mark.asyncio
@patch("vibe_stats.orchestrator.render_report")
@patch("vibe_stats.orchestrator.aggregate_org_report")
@patch("vibe_stats.orchestrator.GitHubClient")
async def test_run_passes_all_params(mock_client_cls, mock_aggregate, mock_render):
    """run() should pass sort_by, exclude_bots, min_commits, output_file."""
    mock_client = AsyncMock()
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_aggregate.return_value = _make_report()

    await run(
        org="test-org",
        token="fake",
        sort_by="additions",
        exclude_bots=True,
        min_commits=5,
        output_file="/tmp/out.txt",
    )

    agg_kwargs = mock_aggregate.call_args.kwargs
    assert agg_kwargs["sort_by"] == "additions"
    assert agg_kwargs["exclude_bots"] is True
    assert agg_kwargs["min_commits"] == 5
    mock_render.assert_called_once()
    render_kwargs = mock_render.call_args
    assert render_kwargs.kwargs.get("output_file") == "/tmp/out.txt" or render_kwargs[1].get("output_file") == "/tmp/out.txt"
