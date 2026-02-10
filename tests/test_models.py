"""Tests for data models."""

from vibe_stats.models import (
    CommitPatternStats,
    ContributorStats,
    ContributorTrend,
    IssueInsights,
    LanguageStats,
    OrgReport,
    PRInsights,
    RepoStats,
)


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
    # New fields should have defaults
    assert rs.stars == 0
    assert rs.forks == 0
    assert rs.size_kb == 0
    assert rs.is_archived is False
    assert rs.primary_language is None
    assert rs.description is None
    assert rs.created_at is None
    assert rs.pushed_at is None
    assert rs.visibility is None
    assert rs.commit_patterns is None
    assert rs.pr_insights is None
    assert rs.issue_insights is None
    assert rs.contributor_trends == []


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
    # New fields should have defaults
    assert report.total_stars == 0
    assert report.total_forks == 0
    assert report.archived_repos == 0
    assert report.commit_patterns is None
    assert report.pr_insights is None
    assert report.issue_insights is None
    assert report.contributor_trends == []


def test_commit_pattern_stats_defaults():
    cp = CommitPatternStats()
    assert cp.feat == 0
    assert cp.fix == 0
    assert cp.other == 0
    assert cp.total == 0
    assert cp.hourly_distribution == {}
    assert cp.weekday_distribution == {}


def test_pr_insights_defaults():
    pri = PRInsights()
    assert pri.total_analyzed == 0
    assert pri.avg_merge_hours is None
    assert pri.median_merge_hours is None
    assert pri.draft_count == 0
    assert pri.top_authors == []


def test_issue_insights_defaults():
    ii = IssueInsights()
    assert ii.total_analyzed == 0
    assert ii.label_distribution == {}
    assert ii.top_reporters == []


def test_contributor_trend_defaults():
    ct = ContributorTrend()
    assert ct.username == ""
    assert ct.first_active_week == ""
    assert ct.last_active_week == ""
    assert ct.active_weeks == 0
    assert ct.total_weeks == 0
