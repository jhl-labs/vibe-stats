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
            "weeks": [{"a": 100, "d": 50, "c": 5}],
        },
        {
            "author": {"login": "bob"},
            "total": 5,
            "weeks": [{"a": 40, "d": 20, "c": 3}],
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
