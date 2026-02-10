"""Data models for vibe-stats."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LanguageStats:
    language: str
    bytes: int
    percentage: float


@dataclass
class ContributorStats:
    username: str
    commits: int
    additions: int
    deletions: int


@dataclass
class CommitPatternStats:
    """Conventional commit type distribution and temporal patterns."""

    feat: int = 0
    fix: int = 0
    refactor: int = 0
    docs: int = 0
    test: int = 0
    chore: int = 0
    style: int = 0
    ci: int = 0
    other: int = 0
    total: int = 0
    hourly_distribution: dict[int, int] = field(default_factory=dict)
    weekday_distribution: dict[int, int] = field(default_factory=dict)


@dataclass
class PRInsights:
    """Pull request merge/close time statistics."""

    total_analyzed: int = 0
    avg_merge_hours: float | None = None
    median_merge_hours: float | None = None
    avg_close_hours: float | None = None
    draft_count: int = 0
    top_authors: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class IssueInsights:
    """Issue label distribution and reporter stats."""

    total_analyzed: int = 0
    label_distribution: dict[str, int] = field(default_factory=dict)
    top_reporters: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class ContributorTrend:
    """Individual contributor activity timeline."""

    username: str = ""
    first_active_week: str = ""
    last_active_week: str = ""
    active_weeks: int = 0
    total_weeks: int = 0


@dataclass
class RepoStats:
    name: str
    full_name: str
    total_commits: int
    total_additions: int
    total_deletions: int
    open_prs: int = 0
    merged_prs: int = 0
    open_issues: int = 0
    languages: list[LanguageStats] = field(default_factory=list)
    contributors: list[ContributorStats] = field(default_factory=list)
    # New fields from list_repos metadata
    stars: int = 0
    forks: int = 0
    size_kb: int = 0
    is_archived: bool = False
    primary_language: str | None = None
    description: str | None = None
    created_at: str | None = None
    pushed_at: str | None = None
    visibility: str | None = None
    # New insight fields
    commit_patterns: CommitPatternStats | None = None
    pr_insights: PRInsights | None = None
    issue_insights: IssueInsights | None = None
    contributor_trends: list[ContributorTrend] = field(default_factory=list)


@dataclass
class OrgReport:
    org: str
    period_start: str | None
    period_end: str | None
    total_repos: int
    total_commits: int
    total_additions: int
    total_deletions: int
    total_open_prs: int = 0
    total_merged_prs: int = 0
    total_open_issues: int = 0
    languages: list[LanguageStats] = field(default_factory=list)
    contributors: list[ContributorStats] = field(default_factory=list)
    repos: list[RepoStats] = field(default_factory=list)
    failed_repos: list[str] = field(default_factory=list)
    # New org-level insight fields
    total_stars: int = 0
    total_forks: int = 0
    archived_repos: int = 0
    commit_patterns: CommitPatternStats | None = None
    pr_insights: PRInsights | None = None
    issue_insights: IssueInsights | None = None
    contributor_trends: list[ContributorTrend] = field(default_factory=list)
