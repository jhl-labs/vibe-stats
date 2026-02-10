"""Tests for the aggregator module."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from vibe_stats.aggregator import (
    _analyze_commit_patterns,
    _analyze_contributor_trends,
    _analyze_issue_insights,
    _analyze_pr_insights,
    _is_bot,
    _sort_key,
    aggregate_org_report,
)
from vibe_stats.github.client import GitHubClient
from vibe_stats.models import ContributorStats


@pytest.fixture
def mock_client():
    client = AsyncMock(spec=GitHubClient)
    client.list_repos.return_value = [
        {
            "name": "repo1", "full_name": "org/repo1",
            "stargazers_count": 10, "forks_count": 3,
            "size": 1024, "archived": False,
            "language": "Python", "description": "A test repo",
            "created_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2024-06-01T00:00:00Z",
            "visibility": "public",
        },
        {
            "name": "repo2", "full_name": "org/repo2",
            "stargazers_count": 5, "forks_count": 1,
            "size": 512, "archived": True,
            "language": "Go", "description": "Another repo",
            "created_at": "2023-06-01T00:00:00Z",
            "pushed_at": "2024-05-01T00:00:00Z",
            "visibility": "private",
        },
    ]
    client.list_commits.return_value = [
        {
            "sha": "abc123",
            "commit": {
                "message": "feat: add new feature",
                "author": {"date": "2024-06-03T10:30:00Z"},  # Monday
            },
        },
        {
            "sha": "def456",
            "commit": {
                "message": "fix: resolve bug",
                "author": {"date": "2024-06-05T14:00:00Z"},  # Wednesday
            },
        },
    ]
    client.get_languages.return_value = {"Python": 5000, "JavaScript": 3000}
    client.get_contributor_stats.return_value = [
        {
            "author": {"login": "alice"},
            "total": 10,
            "weeks": [{"w": 1717200000, "a": 100, "d": 50, "c": 10}],
        },
        {
            "author": {"login": "bob"},
            "total": 5,
            "weeks": [{"w": 1717200000, "a": 40, "d": 20, "c": 5}],
        },
    ]
    client.list_pull_requests.return_value = [
        {
            "state": "open", "merged_at": None, "draft": True,
            "created_at": "2024-06-01T00:00:00Z",
            "closed_at": None,
            "user": {"login": "alice"},
        },
        {
            "state": "closed", "merged_at": "2024-07-01T00:00:00Z",
            "draft": False,
            "created_at": "2024-06-15T00:00:00Z",
            "closed_at": "2024-07-01T00:00:00Z",
            "user": {"login": "bob"},
        },
    ]
    client.list_issues.return_value = [
        {
            "state": "open", "title": "Bug",
            "labels": [{"name": "bug"}, {"name": "priority:high"}],
            "user": {"login": "alice"},
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
    from unittest.mock import patch

    client = AsyncMock(spec=GitHubClient)
    client.list_repos.return_value = [
        {"name": "good-repo", "full_name": "org/good-repo"},
        {"name": "bad-repo", "full_name": "org/bad-repo"},
    ]
    client.list_commits.return_value = [{"sha": "abc123"}]
    client.get_languages.return_value = {"Python": 1000}
    client.get_contributor_stats.return_value = []
    client.list_pull_requests.return_value = []
    client.list_issues.return_value = []

    from vibe_stats.aggregator import _collect_repo_stats as original_collect

    async def patched_collect(cl, owner, name, **kwargs):
        if name == "bad-repo":
            raise RuntimeError("API error")
        return await original_collect(cl, owner, name, **kwargs)

    with patch("vibe_stats.aggregator._collect_repo_stats", side_effect=patched_collect):
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


# --- New insight analysis tests ---


def test_analyze_commit_patterns_conventional():
    """Test conventional commit type classification."""
    commits = [
        {"commit": {"message": "feat: add login", "author": {"date": "2024-06-03T10:00:00Z"}}},
        {"commit": {"message": "fix: resolve crash", "author": {"date": "2024-06-03T14:00:00Z"}}},
        {"commit": {"message": "fix(auth): token expiry", "author": {"date": "2024-06-04T09:00:00Z"}}},
        {"commit": {"message": "docs: update readme", "author": {"date": "2024-06-05T11:00:00Z"}}},
        {"commit": {"message": "refactor!: redesign API", "author": {"date": "2024-06-05T15:00:00Z"}}},
        {"commit": {"message": "chore: bump deps", "author": {"date": "2024-06-06T08:00:00Z"}}},
        {"commit": {"message": "random commit message", "author": {"date": "2024-06-07T12:00:00Z"}}},
        {"commit": {"message": "test: add unit tests", "author": {"date": "2024-06-07T16:00:00Z"}}},
    ]
    result = _analyze_commit_patterns(commits)
    assert result.feat == 1
    assert result.fix == 2
    assert result.docs == 1
    assert result.refactor == 1
    assert result.chore == 1
    assert result.test == 1
    assert result.other == 1
    assert result.total == 8


def test_analyze_commit_patterns_empty():
    """Empty commit list should produce zeroed stats."""
    result = _analyze_commit_patterns([])
    assert result.total == 0
    assert result.feat == 0


def test_analyze_commit_patterns_weekday_distribution():
    """Test weekday distribution extraction."""
    commits = [
        {"commit": {"message": "feat: a", "author": {"date": "2024-06-03T10:00:00Z"}}},  # Mon
        {"commit": {"message": "feat: b", "author": {"date": "2024-06-03T15:00:00Z"}}},  # Mon
        {"commit": {"message": "feat: c", "author": {"date": "2024-06-05T10:00:00Z"}}},  # Wed
    ]
    result = _analyze_commit_patterns(commits)
    assert result.weekday_distribution.get(0) == 2  # Monday
    assert result.weekday_distribution.get(2) == 1  # Wednesday


def test_analyze_commit_patterns_hourly_distribution():
    """Test hourly distribution extraction."""
    commits = [
        {"commit": {"message": "feat: a", "author": {"date": "2024-06-03T10:00:00Z"}}},
        {"commit": {"message": "feat: b", "author": {"date": "2024-06-03T10:30:00Z"}}},
        {"commit": {"message": "feat: c", "author": {"date": "2024-06-03T14:00:00Z"}}},
    ]
    result = _analyze_commit_patterns(commits)
    assert result.hourly_distribution.get(10) == 2
    assert result.hourly_distribution.get(14) == 1


def test_analyze_pr_insights_merge_time():
    """Test PR merge time calculation."""
    prs = [
        {
            "created_at": "2024-06-01T00:00:00Z",
            "merged_at": "2024-06-01T12:00:00Z",
            "closed_at": "2024-06-01T12:00:00Z",
            "state": "closed",
            "draft": False,
            "user": {"login": "alice"},
        },
        {
            "created_at": "2024-06-02T00:00:00Z",
            "merged_at": "2024-06-04T00:00:00Z",
            "closed_at": "2024-06-04T00:00:00Z",
            "state": "closed",
            "draft": False,
            "user": {"login": "bob"},
        },
    ]
    result = _analyze_pr_insights(prs)
    assert result.total_analyzed == 2
    # 12h and 48h -> avg = 30h
    assert result.avg_merge_hours == 30.0
    # median of [12, 48] = 30
    assert result.median_merge_hours == 30.0
    assert result.draft_count == 0


def test_analyze_pr_insights_draft_count():
    """Test draft PR counting."""
    prs = [
        {
            "created_at": "2024-06-01T00:00:00Z",
            "merged_at": None, "closed_at": None,
            "state": "open", "draft": True,
            "user": {"login": "alice"},
        },
        {
            "created_at": "2024-06-02T00:00:00Z",
            "merged_at": None, "closed_at": None,
            "state": "open", "draft": True,
            "user": {"login": "alice"},
        },
    ]
    result = _analyze_pr_insights(prs)
    assert result.draft_count == 2
    assert result.top_authors == [("alice", 2)]


def test_analyze_pr_insights_empty():
    """Empty PR list should return zeroed insights."""
    result = _analyze_pr_insights([])
    assert result.total_analyzed == 0
    assert result.avg_merge_hours is None


def test_analyze_issue_insights_labels():
    """Test issue label distribution."""
    issues = [
        {"labels": [{"name": "bug"}, {"name": "priority:high"}], "user": {"login": "alice"}},
        {"labels": [{"name": "bug"}], "user": {"login": "bob"}},
        {"labels": [{"name": "enhancement"}], "user": {"login": "alice"}},
    ]
    result = _analyze_issue_insights(issues)
    assert result.total_analyzed == 3
    assert result.label_distribution["bug"] == 2
    assert result.label_distribution["priority:high"] == 1
    assert result.label_distribution["enhancement"] == 1
    assert result.top_reporters[0] == ("alice", 2)


def test_analyze_issue_insights_empty():
    """Empty issue list should return zeroed insights."""
    result = _analyze_issue_insights([])
    assert result.total_analyzed == 0
    assert result.label_distribution == {}


def test_analyze_contributor_trends():
    """Test contributor activity timeline analysis."""
    raw = [
        {
            "author": {"login": "alice"},
            "weeks": [
                {"w": 1717200000, "a": 10, "d": 5, "c": 3},
                {"w": 1717804800, "a": 0, "d": 0, "c": 0},  # inactive week
                {"w": 1718409600, "a": 20, "d": 10, "c": 5},
            ],
        },
        {
            "author": {"login": "bob"},
            "weeks": [
                {"w": 1717200000, "a": 5, "d": 2, "c": 1},
            ],
        },
    ]
    result = _analyze_contributor_trends(raw)
    assert len(result) == 2
    # alice has 2 active weeks, bob has 1
    alice = next(t for t in result if t.username == "alice")
    bob = next(t for t in result if t.username == "bob")
    assert alice.active_weeks == 2
    assert bob.active_weeks == 1


def test_analyze_contributor_trends_empty():
    """Empty contributor list should return empty trends."""
    result = _analyze_contributor_trends([])
    assert result == []


def test_analyze_contributor_trends_no_author():
    """Contributors with no author should be skipped."""
    raw = [
        {"author": None, "weeks": [{"w": 1717200000, "a": 10, "d": 5, "c": 3}]},
    ]
    result = _analyze_contributor_trends(raw)
    assert result == []


# --- Integration tests for new org-level insights ---


@pytest.mark.asyncio
async def test_aggregate_org_report_stars_forks(mock_client):
    """Org report should aggregate stars and forks from repos."""
    report = await aggregate_org_report(mock_client, "org")
    assert report.total_stars == 15  # 10 + 5
    assert report.total_forks == 4  # 3 + 1
    assert report.archived_repos == 1  # repo2 is archived


@pytest.mark.asyncio
async def test_aggregate_org_report_commit_patterns(mock_client):
    """Org report should have aggregated commit patterns."""
    report = await aggregate_org_report(mock_client, "org")
    cp = report.commit_patterns
    assert cp is not None
    assert cp.total == 4  # 2 commits * 2 repos
    assert cp.feat >= 1
    assert cp.fix >= 1


@pytest.mark.asyncio
async def test_aggregate_org_report_pr_insights(mock_client):
    """Org report should have aggregated PR insights."""
    report = await aggregate_org_report(mock_client, "org")
    pri = report.pr_insights
    assert pri is not None
    assert pri.total_analyzed == 4  # 2 PRs * 2 repos
    assert pri.draft_count == 2  # 1 draft PR * 2 repos


@pytest.mark.asyncio
async def test_aggregate_org_report_issue_insights(mock_client):
    """Org report should have aggregated issue insights."""
    report = await aggregate_org_report(mock_client, "org")
    ii = report.issue_insights
    assert ii is not None
    assert ii.total_analyzed == 2  # 1 issue * 2 repos
    assert ii.label_distribution.get("bug") == 2


@pytest.mark.asyncio
async def test_aggregate_org_report_contributor_trends(mock_client):
    """Org report should have aggregated contributor trends."""
    report = await aggregate_org_report(mock_client, "org")
    assert len(report.contributor_trends) >= 1


@pytest.mark.asyncio
async def test_repo_stats_metadata(mock_client):
    """Repo stats should include metadata from list_repos response."""
    report = await aggregate_org_report(mock_client, "org")
    repo1 = next(r for r in report.repos if r.name == "repo1")
    assert repo1.stars == 10
    assert repo1.forks == 3
    assert repo1.primary_language == "Python"
    assert repo1.visibility == "public"
    assert repo1.is_archived is False

    repo2 = next(r for r in report.repos if r.name == "repo2")
    assert repo2.stars == 5
    assert repo2.is_archived is True
