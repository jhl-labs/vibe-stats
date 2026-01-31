"""Tests for the aggregator module."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from vibe_stats.aggregator import _is_bot, _sort_key, aggregate_org_report
from vibe_stats.github.client import GitHubClient
from vibe_stats.models import ContributorStats


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
    client.list_pull_requests.return_value = [
        {"state": "open", "merged_at": None, "created_at": "2024-06-01T00:00:00Z"},
        {"state": "closed", "merged_at": "2024-07-01T00:00:00Z", "created_at": "2024-06-15T00:00:00Z"},
    ]
    client.list_issues.return_value = [
        {"state": "open", "title": "Bug"},
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
    client.list_pull_requests.return_value = []
    client.list_issues.return_value = []

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


# --- New feature tests ---


def test_is_bot_with_bot_suffix():
    assert _is_bot("dependabot[bot]") is True
    assert _is_bot("renovate[bot]") is True
    assert _is_bot("SomeBot[bot]") is True


def test_is_bot_known_bots():
    assert _is_bot("dependabot") is True
    assert _is_bot("renovate") is True
    assert _is_bot("github-actions") is True
    assert _is_bot("codecov") is True
    assert _is_bot("snyk-bot") is True


def test_is_bot_regular_users():
    assert _is_bot("alice") is False
    assert _is_bot("bob") is False
    assert _is_bot("my-bot-project") is False


def test_sort_key_commits():
    key_fn = _sort_key("commits")
    c = ContributorStats(username="a", commits=10, additions=20, deletions=5)
    assert key_fn(c) == 10


def test_sort_key_additions():
    key_fn = _sort_key("additions")
    c = ContributorStats(username="a", commits=10, additions=20, deletions=5)
    assert key_fn(c) == 20


def test_sort_key_deletions():
    key_fn = _sort_key("deletions")
    c = ContributorStats(username="a", commits=10, additions=20, deletions=5)
    assert key_fn(c) == 5


def test_sort_key_lines():
    key_fn = _sort_key("lines")
    c = ContributorStats(username="a", commits=10, additions=20, deletions=5)
    assert key_fn(c) == 25


@pytest.mark.asyncio
async def test_aggregate_exclude_bots(mock_client):
    """Bot contributors should be excluded when exclude_bots=True."""
    mock_client.get_contributor_stats.return_value = [
        {
            "author": {"login": "alice"},
            "total": 10,
            "weeks": [{"w": 0, "a": 100, "d": 50, "c": 10}],
        },
        {
            "author": {"login": "dependabot[bot]"},
            "total": 3,
            "weeks": [{"w": 0, "a": 10, "d": 5, "c": 3}],
        },
        {
            "author": {"login": "renovate"},
            "total": 2,
            "weeks": [{"w": 0, "a": 5, "d": 2, "c": 2}],
        },
    ]
    report = await aggregate_org_report(mock_client, "org", exclude_bots=True)
    usernames = [c.username for c in report.contributors]
    assert "alice" in usernames
    assert "dependabot[bot]" not in usernames
    assert "renovate" not in usernames


@pytest.mark.asyncio
async def test_aggregate_sort_by_additions(mock_client):
    """Contributors should be sorted by additions when sort_by='additions'."""
    report = await aggregate_org_report(mock_client, "org", sort_by="additions")
    # alice has 200 additions (100*2 repos), bob has 80 (40*2 repos)
    assert report.contributors[0].username == "alice"
    assert report.contributors[1].username == "bob"


@pytest.mark.asyncio
async def test_aggregate_min_commits(mock_client):
    """Contributors below min_commits threshold should be excluded."""
    # alice: 20 commits (10*2), bob: 10 commits (5*2)
    report = await aggregate_org_report(mock_client, "org", min_commits=15)
    assert len(report.contributors) == 1
    assert report.contributors[0].username == "alice"


@pytest.mark.asyncio
async def test_aggregate_min_commits_zero_no_filter(mock_client):
    """min_commits=0 should not filter any contributors."""
    report = await aggregate_org_report(mock_client, "org", min_commits=0)
    assert len(report.contributors) == 2


@pytest.mark.asyncio
async def test_aggregate_pr_issue_stats(mock_client):
    """PR and issue stats should be aggregated."""
    report = await aggregate_org_report(mock_client, "org")
    # 2 repos, each with 1 open PR, 1 merged PR, 1 open issue
    assert report.total_open_prs == 2
    assert report.total_merged_prs == 2
    assert report.total_open_issues == 2


@pytest.mark.asyncio
async def test_aggregate_contributor_no_author(mock_client):
    """Contributors with no author should be skipped."""
    mock_client.get_contributor_stats.return_value = [
        {
            "author": None,
            "total": 5,
            "weeks": [{"w": 0, "a": 10, "d": 5, "c": 5}],
        },
        {
            "author": {"login": "alice"},
            "total": 10,
            "weeks": [{"w": 0, "a": 100, "d": 50, "c": 10}],
        },
    ]
    report = await aggregate_org_report(mock_client, "org", repo="single-repo")
    # Only alice should appear (None author skipped)
    assert len(report.contributors) == 1
    assert report.contributors[0].username == "alice"


@pytest.mark.asyncio
async def test_aggregate_contributor_until_filter(mock_client):
    """Contributors with weeks after until should be filtered."""
    # week_start=2000000000 is far in the future (~2033)
    mock_client.get_contributor_stats.return_value = [
        {
            "author": {"login": "alice"},
            "total": 10,
            "weeks": [
                {"w": 1704067200, "a": 50, "d": 20, "c": 5},  # 2024-01-01
                {"w": 2000000000, "a": 50, "d": 30, "c": 5},  # far future
            ],
        },
    ]
    report = await aggregate_org_report(
        mock_client, "org", repo="single-repo",
        until="2024-12-31T23:59:59Z",
    )
    # Only the first week should count (second week is after until)
    assert report.contributors[0].additions == 50
    assert report.contributors[0].commits == 5
