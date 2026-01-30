"""Tests for the aggregator module."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from vibe_stats.aggregator import aggregate_org_report
from vibe_stats.github.client import GitHubClient


@pytest.fixture
def mock_client():
    client = AsyncMock(spec=GitHubClient)
    client.list_repos.return_value = [
        {"name": "repo1", "full_name": "org/repo1"},
        {"name": "repo2", "full_name": "org/repo2"},
    ]
    client.list_commits.return_value = [
        {"sha": "abc123"},
        {"sha": "def456"},
    ]
    client.get_languages.return_value = {"Python": 5000, "JavaScript": 3000}
    client.get_contributor_stats.return_value = [
        {
            "author": {"login": "alice"},
            "total": 10,
            "weeks": [{"w": 0, "a": 100, "d": 50, "c": 10}],
        },
        {
            "author": {"login": "bob"},
            "total": 5,
            "weeks": [{"w": 0, "a": 40, "d": 20, "c": 5}],
        },
    ]
    return client


@pytest.mark.asyncio
async def test_aggregate_org_report(mock_client):
    report = await aggregate_org_report(mock_client, "org")

    assert report.org == "org"
    assert report.total_repos == 2
    # 2 commits per repo * 2 repos = 4
    assert report.total_commits == 4
    # Language aggregation: Python 5000*2=10000, JS 3000*2=6000
    assert len(report.languages) == 2
    assert report.languages[0].language == "Python"
    assert report.languages[0].bytes == 10000
    # Contributors aggregated across repos
    assert len(report.contributors) == 2
    assert report.contributors[0].username == "alice"
    assert report.contributors[0].commits == 20  # 10 * 2 repos


@pytest.mark.asyncio
async def test_aggregate_handles_empty_org():
    client = AsyncMock(spec=GitHubClient)
    client.list_repos.return_value = []
    report = await aggregate_org_report(client, "empty-org")
    assert report.total_repos == 0
    assert report.total_commits == 0


@pytest.mark.asyncio
async def test_aggregate_error_recovery():
    """Failed repos should be skipped and recorded in failed_repos."""
    client = AsyncMock(spec=GitHubClient)
    client.list_repos.return_value = [
        {"name": "good-repo", "full_name": "org/good-repo"},
        {"name": "bad-repo", "full_name": "org/bad-repo"},
    ]

    async def commits_side_effect(owner, repo, **kwargs):
        if repo == "bad-repo":
            raise RuntimeError("API error")
        return [{"sha": "abc123"}]

    client.list_commits.side_effect = commits_side_effect
    client.get_languages.return_value = {"Python": 1000}
    client.get_contributor_stats.return_value = []

    report = await aggregate_org_report(client, "org")

    assert report.total_repos == 1
    assert report.failed_repos == ["bad-repo"]
    assert report.total_commits == 1


@pytest.mark.asyncio
async def test_aggregate_since_until_passed(mock_client):
    """since/until should be passed to list_commits and set on report."""
    report = await aggregate_org_report(
        mock_client, "org", since="2024-01-01T00:00:00Z", until="2024-12-31T23:59:59Z"
    )
    assert report.period_start == "2024-01-01T00:00:00Z"
    assert report.period_end == "2024-12-31T23:59:59Z"
    # Verify since/until were passed to list_commits
    for call in mock_client.list_commits.call_args_list:
        assert call.kwargs.get("since") == "2024-01-01T00:00:00Z"
        assert call.kwargs.get("until") == "2024-12-31T23:59:59Z"


@pytest.mark.asyncio
async def test_aggregate_include_forks(mock_client):
    """include_forks should be passed to list_repos."""
    await aggregate_org_report(mock_client, "org", include_forks=True)
    mock_client.list_repos.assert_called_once_with("org", include_forks=True)


@pytest.mark.asyncio
async def test_aggregate_single_repo(mock_client):
    """When repo is specified, only that repo should be analyzed."""
    report = await aggregate_org_report(mock_client, "org", repo="my-repo")
    # Should NOT call list_repos when a specific repo is given
    mock_client.list_repos.assert_not_called()
    assert report.total_repos == 1
    assert report.repos[0].name == "my-repo"


@pytest.mark.asyncio
async def test_aggregate_exclude_repos(mock_client):
    """Excluded repos should be filtered out."""
    report = await aggregate_org_report(mock_client, "org", exclude_repos=["repo2"])
    assert report.total_repos == 1
    assert report.repos[0].name == "repo1"


@pytest.mark.asyncio
async def test_aggregate_exclude_multiple_repos(mock_client):
    """Multiple repos can be excluded."""
    report = await aggregate_org_report(mock_client, "org", exclude_repos=["repo1", "repo2"])
    assert report.total_repos == 0
