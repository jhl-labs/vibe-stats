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
class RepoStats:
    name: str
    full_name: str
    total_commits: int
    total_additions: int
    total_deletions: int
    languages: list[LanguageStats] = field(default_factory=list)
    contributors: list[ContributorStats] = field(default_factory=list)


@dataclass
class OrgReport:
    org: str
    period_start: str | None
    period_end: str | None
    total_repos: int
    total_commits: int
    total_additions: int
    total_deletions: int
    languages: list[LanguageStats] = field(default_factory=list)
    contributors: list[ContributorStats] = field(default_factory=list)
    repos: list[RepoStats] = field(default_factory=list)
    failed_repos: list[str] = field(default_factory=list)
