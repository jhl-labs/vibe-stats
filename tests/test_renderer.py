"""Tests for the renderer module."""

from __future__ import annotations

import json
import os
import tempfile

from vibe_stats.models import (
    CommitPatternStats,
    ContributorStats,
    IssueInsights,
    LanguageStats,
    OrgReport,
    PRInsights,
    RepoStats,
)
from vibe_stats.renderer import render_csv, render_json, render_report


def _make_report(**kwargs) -> OrgReport:
    defaults = dict(
        org="test-org",
        period_start=None,
        period_end=None,
        total_repos=1,
        total_commits=10,
        total_additions=100,
        total_deletions=50,
        total_open_prs=3,
        total_merged_prs=5,
        total_open_issues=2,
        languages=[LanguageStats(language="Python", bytes=1000, percentage=100.0)],
        contributors=[
            ContributorStats(username="alice", commits=7, additions=70, deletions=30),
            ContributorStats(username="bob", commits=3, additions=30, deletions=20),
        ],
        repos=[],
        failed_repos=[],
        total_stars=42,
        total_forks=10,
        archived_repos=0,
    )
    defaults.update(kwargs)
    return OrgReport(**defaults)


def test_render_report_no_error(capsys):
    """render_report should run without error."""
    report = _make_report()
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "test-org" in captured.out
    assert "alice" in captured.out


def test_render_report_shows_failed_repos(capsys):
    """render_report should show warning for failed repos."""
    report = _make_report(failed_repos=["broken-repo"])
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "broken-repo" in captured.out


def test_render_json(capsys):
    """render_json should output valid JSON."""
    report = _make_report()
    render_json(report)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["org"] == "test-org"
    assert data["total_commits"] == 10
    assert len(data["contributors"]) == 2


def test_render_csv(capsys):
    """render_csv should output valid CSV with header and rows."""
    report = _make_report()
    render_csv(report)
    captured = capsys.readouterr()
    lines = [line.strip() for line in captured.out.strip().split("\n")]
    assert lines[0] == "username,commits,additions,deletions"
    assert lines[1] == "alice,7,70,30"
    assert lines[2] == "bob,3,30,20"


def test_render_report_shows_pr_issue_stats(capsys):
    """render_report should show PR and issue statistics in summary."""
    report = _make_report()
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "Open PRs" in captured.out
    assert "Merged PRs" in captured.out
    assert "Open Issues" in captured.out


def test_render_report_sort_indicator(capsys):
    """render_report should show sort indicator on the sorted column."""
    report = _make_report()
    render_report(report, top_n=5, sort_by="additions")
    captured = capsys.readouterr()
    assert "\u25bc" in captured.out  # down arrow


def test_render_report_repo_summary_multi_repos(capsys):
    """render_report should show repo summary table when multiple repos exist."""
    repos = [
        RepoStats(
            name="repo1", full_name="org/repo1",
            total_commits=5, total_additions=50, total_deletions=20,
            stars=10, forks=3,
            languages=[LanguageStats(language="Python", bytes=500, percentage=100.0)],
        ),
        RepoStats(
            name="repo2", full_name="org/repo2",
            total_commits=3, total_additions=30, total_deletions=10,
            stars=5, forks=1,
            languages=[LanguageStats(language="Go", bytes=300, percentage=100.0)],
        ),
    ]
    report = _make_report(repos=repos, total_repos=2)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "Repository Summary" in captured.out
    assert "repo1" in captured.out
    assert "repo2" in captured.out
    assert "Stars" in captured.out
    assert "Forks" in captured.out


def test_render_report_no_repo_summary_single_repo(capsys):
    """render_report should NOT show repo summary when only one repo."""
    repos = [
        RepoStats(
            name="repo1", full_name="org/repo1",
            total_commits=5, total_additions=50, total_deletions=20,
        ),
    ]
    report = _make_report(repos=repos, total_repos=1)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "Repository Summary" not in captured.out


def test_render_json_to_file():
    """render_json should write to file when output_file is specified."""
    report = _make_report()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        render_json(report, output_file=path)
        with open(path) as f:
            data = json.loads(f.read())
        assert data["org"] == "test-org"
    finally:
        os.unlink(path)


def test_render_csv_to_file():
    """render_csv should write to file when output_file is specified."""
    report = _make_report()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        path = f.name
    try:
        render_csv(report, output_file=path)
        with open(path) as f:
            content = f.read()
        assert "alice,7,70,30" in content
    finally:
        os.unlink(path)


def test_render_report_to_file():
    """render_report should write to file when output_file is specified."""
    report = _make_report()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        path = f.name
    try:
        render_report(report, top_n=5, output_file=path)
        with open(path) as f:
            content = f.read()
        assert "test-org" in content
    finally:
        os.unlink(path)


def test_render_report_with_period(capsys):
    """render_report should show period when start/end are set."""
    report = _make_report(
        period_start="2024-01-01T00:00:00Z",
        period_end="2024-12-31T23:59:59Z",
    )
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "Period:" in captured.out
    assert "2024-01-01" in captured.out


def test_render_report_sort_by_lines(capsys):
    """render_report should show Lines column when sort_by=lines."""
    report = _make_report()
    render_report(report, top_n=5, sort_by="lines")
    captured = capsys.readouterr()
    assert "Lines" in captured.out
    # alice: 70+30=100
    assert "100" in captured.out


# --- New section tests ---


def test_render_report_shows_stars_forks(capsys):
    """render_report should show total stars and forks in summary when > 0."""
    report = _make_report(total_stars=42, total_forks=10)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "Total Stars" in captured.out
    assert "42" in captured.out
    assert "Total Forks" in captured.out
    assert "10" in captured.out


def test_render_report_hides_stars_forks_when_zero(capsys):
    """render_report should NOT show stars/forks in summary when 0."""
    report = _make_report(total_stars=0, total_forks=0)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "Total Stars" not in captured.out
    assert "Total Forks" not in captured.out


def test_render_report_shows_archived_repos(capsys):
    """render_report should show archived repos count when > 0."""
    report = _make_report(archived_repos=3)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "Archived Repos" in captured.out
    assert "3" in captured.out


def test_render_report_hides_archived_when_zero(capsys):
    """render_report should NOT show archived repos when 0."""
    report = _make_report(archived_repos=0)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "Archived Repos" not in captured.out


def test_render_report_repo_summary_conditional_stars_forks(capsys):
    """Stars/Forks columns should only appear when repos have nonzero values."""
    repos = [
        RepoStats(
            name="repo1", full_name="org/repo1",
            total_commits=5, total_additions=50, total_deletions=20,
            stars=0, forks=0,
            languages=[LanguageStats(language="Python", bytes=500, percentage=100.0)],
        ),
        RepoStats(
            name="repo2", full_name="org/repo2",
            total_commits=3, total_additions=30, total_deletions=10,
            stars=0, forks=0,
            languages=[LanguageStats(language="Go", bytes=300, percentage=100.0)],
        ),
    ]
    report = _make_report(repos=repos, total_repos=2, total_stars=0, total_forks=0)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "Repository Summary" in captured.out
    # Stars/Forks columns should be hidden when all repos have 0
    assert "Stars" not in captured.out
    assert "Forks" not in captured.out


def test_render_report_repo_summary_archived_marker(capsys):
    """Archived repos should show [A] marker in repo summary."""
    repos = [
        RepoStats(
            name="active-repo", full_name="org/active-repo",
            total_commits=5, total_additions=50, total_deletions=20,
            is_archived=False,
        ),
        RepoStats(
            name="old-repo", full_name="org/old-repo",
            total_commits=2, total_additions=10, total_deletions=5,
            is_archived=True,
        ),
    ]
    report = _make_report(repos=repos, total_repos=2, total_stars=0, total_forks=0)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "old-repo" in captured.out
    assert "A" in captured.out  # archived marker


def test_render_report_repo_summary_changes_column(capsys):
    """Repo summary should show +/- column with additions and deletions."""
    repos = [
        RepoStats(
            name="repo1", full_name="org/repo1",
            total_commits=5, total_additions=50, total_deletions=20,
        ),
        RepoStats(
            name="repo2", full_name="org/repo2",
            total_commits=3, total_additions=30, total_deletions=10,
        ),
    ]
    report = _make_report(repos=repos, total_repos=2, total_stars=0, total_forks=0)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "+/-" in captured.out
    assert "+50" in captured.out
    assert "-20" in captured.out


def test_render_report_commit_patterns(capsys):
    """render_report should show commit patterns section."""
    cp = CommitPatternStats(
        feat=5, fix=3, refactor=2, docs=1, test=1, chore=1, style=0, ci=0, other=2,
        total=15,
        weekday_distribution={0: 5, 1: 3, 2: 4, 3: 2, 4: 1},
    )
    report = _make_report(commit_patterns=cp)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "Commit Patterns" in captured.out
    assert "feat" in captured.out
    assert "fix" in captured.out
    assert "Commits by Day of Week" in captured.out
    assert "Mon" in captured.out


def test_render_report_commit_patterns_peak_hours(capsys):
    """render_report should show peak hours when hourly distribution exists."""
    cp = CommitPatternStats(
        feat=5, fix=3, total=8,
        hourly_distribution={10: 15, 14: 10, 16: 8, 9: 5},
    )
    report = _make_report(commit_patterns=cp)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "Peak hours" in captured.out
    assert "10:00" in captured.out


def test_render_report_pr_insights(capsys):
    """render_report should show PR insights section."""
    pri = PRInsights(
        total_analyzed=20,
        avg_merge_hours=24.5,
        median_merge_hours=18.0,
        draft_count=3,
        top_authors=[("alice", 10), ("bob", 7)],
    )
    report = _make_report(pr_insights=pri)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "PR Insights" in captured.out
    assert "Avg Merge Time" in captured.out
    assert "Median Merge Time" in captured.out
    assert "Top PR Authors" in captured.out
    assert "alice" in captured.out


def test_render_report_pr_authors_sorted(capsys):
    """Top PR Authors should be sorted by count descending."""
    pri = PRInsights(
        total_analyzed=10,
        top_authors=[("bob", 3), ("alice", 7), ("carol", 5)],
    )
    report = _make_report(pr_insights=pri)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    # alice(7) should appear before carol(5) before bob(3)
    alice_pos = captured.out.index("alice")
    carol_pos = captured.out.index("carol")
    bob_pos = captured.out.index("bob")
    # Within the PR Authors table section only
    assert alice_pos < carol_pos < bob_pos


def test_render_report_issue_insights(capsys):
    """render_report should show issue insights section."""
    ii = IssueInsights(
        total_analyzed=10,
        label_distribution={"bug": 5, "enhancement": 3, "question": 2},
        top_reporters=[("alice", 4), ("bob", 3)],
    )
    report = _make_report(issue_insights=ii)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "Issue Insights" in captured.out
    assert "bug" in captured.out
    assert "Top Issue Reporters" in captured.out
    assert "alice" in captured.out


def test_render_report_contributor_trends(capsys):
    """render_report should show contributor activity trends."""
    from vibe_stats.models import ContributorTrend

    trends = [
        ContributorTrend(
            username="alice",
            first_active_week="2024-01-01",
            last_active_week="2024-06-01",
            active_weeks=20,
            total_weeks=22,
        ),
        ContributorTrend(
            username="bob",
            first_active_week="2024-03-01",
            last_active_week="2024-05-01",
            active_weeks=8,
            total_weeks=9,
        ),
    ]
    report = _make_report(contributor_trends=trends)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "Contributor Activity" in captured.out
    assert "alice" in captured.out
    assert "bob" in captured.out
    assert "First Active" in captured.out
    assert "Last Active" in captured.out
    # alice: 20/22 = 91%
    assert "91%" in captured.out


def test_render_report_no_contributor_trends_when_empty(capsys):
    """render_report should NOT show trends section when empty."""
    report = _make_report(contributor_trends=[])
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "Contributor Activity" not in captured.out


def test_render_json_includes_new_fields(capsys):
    """render_json should include new insight fields."""
    cp = CommitPatternStats(feat=5, fix=3, total=8)
    pri = PRInsights(total_analyzed=10, avg_merge_hours=24.0)
    ii = IssueInsights(total_analyzed=5, label_distribution={"bug": 3})
    report = _make_report(
        total_stars=42, total_forks=10, archived_repos=1,
        commit_patterns=cp, pr_insights=pri, issue_insights=ii,
    )
    render_json(report)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["total_stars"] == 42
    assert data["total_forks"] == 10
    assert data["archived_repos"] == 1
    assert data["commit_patterns"]["feat"] == 5
    assert data["pr_insights"]["total_analyzed"] == 10
    assert data["issue_insights"]["label_distribution"]["bug"] == 3
