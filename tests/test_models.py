"""Tests for data models."""

from vibe_stats.models import ContributorStats, LanguageStats, OrgReport, RepoStats


def test_language_stats():
    ls = LanguageStats(language="Python", bytes=1000, percentage=50.0)
    assert ls.language == "Python"
    assert ls.bytes == 1000
    assert ls.percentage == 50.0


def test_contributor_stats():
    cs = ContributorStats(username="alice", commits=10, additions=100, deletions=50)
    assert cs.username == "alice"
    assert cs.commits == 10


def test_repo_stats_defaults():
    rs = RepoStats(
        name="repo1",
        full_name="org/repo1",
        total_commits=5,
        total_additions=100,
        total_deletions=50,
    )
    assert rs.languages == []
    assert rs.contributors == []


def test_org_report():
    report = OrgReport(
        org="test-org",
        period_start=None,
        period_end=None,
        total_repos=2,
        total_commits=100,
        total_additions=5000,
        total_deletions=2000,
    )
    assert report.org == "test-org"
    assert report.total_repos == 2
    assert report.repos == []
