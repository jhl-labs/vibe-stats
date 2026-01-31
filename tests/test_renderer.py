"""Tests for the renderer module."""

from __future__ import annotations

import json
import os
import tempfile

from vibe_stats.models import ContributorStats, LanguageStats, OrgReport, RepoStats
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
            languages=[LanguageStats(language="Python", bytes=500, percentage=100.0)],
        ),
        RepoStats(
            name="repo2", full_name="org/repo2",
            total_commits=3, total_additions=30, total_deletions=10,
            languages=[LanguageStats(language="Go", bytes=300, percentage=100.0)],
        ),
    ]
    report = _make_report(repos=repos, total_repos=2)
    render_report(report, top_n=5)
    captured = capsys.readouterr()
    assert "Repository Summary" in captured.out
    assert "repo1" in captured.out
    assert "repo2" in captured.out


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
