"""Tests for the renderer module."""

from __future__ import annotations

import json

from vibe_stats.models import ContributorStats, LanguageStats, OrgReport
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
