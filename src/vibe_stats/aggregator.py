"""Data aggregation: collect per-repo stats and produce an OrgReport."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone

from rich.progress import Progress, SpinnerColumn, TextColumn

from .github.client import GitHubClient
from .models import ContributorStats, LanguageStats, OrgReport, RepoStats

logger = logging.getLogger(__name__)

KNOWN_BOTS = frozenset({
    "dependabot",
    "renovate",
    "github-actions",
    "codecov",
    "snyk-bot",
    "greenkeeper",
    "dependabot-preview",
    "renovate-bot",
    "allcontributors",
    "imgbot",
    "stale",
    "mergify",
    "sonarcloud",
})


def _is_bot(username: str) -> bool:
    """Check if a username belongs to a bot account."""
    lower = username.lower()
    if lower.endswith("[bot]"):
        return True
    return lower in KNOWN_BOTS


def _sort_key(sort_by: str):
    """Return a sort key function for ContributorStats."""
    if sort_by == "additions":
        return lambda c: c.additions
    elif sort_by == "deletions":
        return lambda c: c.deletions
    elif sort_by == "lines":
        return lambda c: c.additions + c.deletions
    else:  # commits
        return lambda c: c.commits


async def _collect_repo_stats(
    client: GitHubClient,
    owner: str,
    repo_name: str,
    since: str | None = None,
    until: str | None = None,
) -> RepoStats:
    """Collect stats for a single repository."""
    commits_task = asyncio.create_task(
        client.list_commits(owner, repo_name, since=since, until=until)
    )
    languages_task = asyncio.create_task(client.get_languages(owner, repo_name))
    contributors_task = asyncio.create_task(client.get_contributor_stats(owner, repo_name))
    prs_task = asyncio.create_task(
        client.list_pull_requests(owner, repo_name, state="all", since=since, until=until)
    )
    issues_task = asyncio.create_task(
        client.list_issues(owner, repo_name, state="open", since=since)
    )

    commits, lang_bytes, raw_contributors, prs, issues = await asyncio.gather(
        commits_task, languages_task, contributors_task, prs_task, issues_task
    )

    # Commits
    total_commits = len(commits) if isinstance(commits, list) else 0

    # PRs
    open_prs = 0
    merged_prs = 0
    if isinstance(prs, list):
        for pr in prs:
            if pr.get("merged_at"):
                merged_prs += 1
            elif pr.get("state") == "open":
                open_prs += 1

    # Issues
    open_issues = len(issues) if isinstance(issues, list) else 0

    # Languages
    languages: list[LanguageStats] = []
    if isinstance(lang_bytes, dict) and lang_bytes:
        total_bytes = sum(lang_bytes.values())
        for lang, b in sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True):
            languages.append(LanguageStats(
                language=lang,
                bytes=b,
                percentage=round(b / total_bytes * 100, 1) if total_bytes else 0,
            ))

    # Contributors — filter weeks by since/until when provided
    since_ts: float | None = None
    until_ts: float | None = None
    if since:
        since_ts = datetime.fromisoformat(since.replace("Z", "+00:00")).timestamp()
    if until:
        until_ts = datetime.fromisoformat(until.replace("Z", "+00:00")).timestamp()

    contributors: list[ContributorStats] = []
    total_additions = 0
    total_deletions = 0
    if isinstance(raw_contributors, list):
        for c in raw_contributors:
            author = c.get("author")
            if not author:
                continue
            weeks = c.get("weeks", [])
            filtered_weeks = []
            for w in weeks:
                week_start = w.get("w", 0)
                if since_ts is not None and week_start + 7 * 86400 <= since_ts:
                    continue
                if until_ts is not None and week_start > until_ts:
                    continue
                filtered_weeks.append(w)
            additions = sum(w.get("a", 0) for w in filtered_weeks)
            deletions = sum(w.get("d", 0) for w in filtered_weeks)
            commits_count = sum(w.get("c", 0) for w in filtered_weeks)
            if commits_count == 0 and additions == 0 and deletions == 0:
                continue
            total_additions += additions
            total_deletions += deletions
            contributors.append(ContributorStats(
                username=author.get("login", "unknown"),
                commits=commits_count,
                additions=additions,
                deletions=deletions,
            ))
        contributors.sort(key=lambda x: x.commits, reverse=True)

    return RepoStats(
        name=repo_name,
        full_name=f"{owner}/{repo_name}",
        total_commits=total_commits,
        total_additions=total_additions,
        total_deletions=total_deletions,
        open_prs=open_prs,
        merged_prs=merged_prs,
        open_issues=open_issues,
        languages=languages,
        contributors=contributors,
    )


async def aggregate_org_report(
    client: GitHubClient,
    org: str,
    since: str | None = None,
    until: str | None = None,
    include_forks: bool = False,
    repo: str | None = None,
    exclude_repos: list[str] | None = None,
    sort_by: str = "commits",
    exclude_bots: bool = False,
    min_commits: int = 0,
) -> OrgReport:
    """Aggregate statistics for all repos in an organization or a single repo."""
    if repo:
        # Single repo mode: fetch repo metadata to build a minimal dict
        repos = [{"name": repo}]
    else:
        repos = await client.list_repos(org, include_forks=include_forks)

    if exclude_repos:
        excluded = set(exclude_repos)
        repos = [r for r in repos if r["name"] not in excluded]

    repo_stats_list: list[RepoStats] = []
    failed_repos: list[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task(f"Collecting stats for {len(repos)} repos...", total=len(repos))

        async def collect_and_update(repo: dict) -> RepoStats | None:
            name = repo["name"]
            try:
                stats = await _collect_repo_stats(
                    client, org, name, since=since, until=until
                )
                return stats
            except Exception:
                logger.warning("Failed to collect stats for %s/%s", org, name)
                failed_repos.append(name)
                return None
            finally:
                progress.advance(task)

        results = await asyncio.gather(
            *(collect_and_update(r) for r in repos)
        )
        repo_stats_list = [r for r in results if r is not None]

    # Aggregate org-level stats
    total_commits = sum(r.total_commits for r in repo_stats_list)
    total_additions = sum(r.total_additions for r in repo_stats_list)
    total_deletions = sum(r.total_deletions for r in repo_stats_list)
    total_open_prs = sum(r.open_prs for r in repo_stats_list)
    total_merged_prs = sum(r.merged_prs for r in repo_stats_list)
    total_open_issues = sum(r.open_issues for r in repo_stats_list)

    # Aggregate languages
    lang_totals: dict[str, int] = defaultdict(int)
    for r in repo_stats_list:
        for lang in r.languages:
            lang_totals[lang.language] += lang.bytes
    total_lang_bytes = sum(lang_totals.values())
    org_languages = [
        LanguageStats(
            language=lang,
            bytes=b,
            percentage=round(b / total_lang_bytes * 100, 1) if total_lang_bytes else 0,
        )
        for lang, b in sorted(lang_totals.items(), key=lambda x: x[1], reverse=True)
    ]

    # Aggregate contributors
    contrib_totals: dict[str, ContributorStats] = {}
    for r in repo_stats_list:
        for c in r.contributors:
            if c.username in contrib_totals:
                existing = contrib_totals[c.username]
                contrib_totals[c.username] = ContributorStats(
                    username=c.username,
                    commits=existing.commits + c.commits,
                    additions=existing.additions + c.additions,
                    deletions=existing.deletions + c.deletions,
                )
            else:
                contrib_totals[c.username] = ContributorStats(
                    username=c.username,
                    commits=c.commits,
                    additions=c.additions,
                    deletions=c.deletions,
                )

    org_contributors = list(contrib_totals.values())

    # Filter bots
    if exclude_bots:
        org_contributors = [c for c in org_contributors if not _is_bot(c.username)]

    # Filter by min-commits
    if min_commits > 0:
        org_contributors = [c for c in org_contributors if c.commits >= min_commits]

    # Sort by chosen metric
    org_contributors.sort(key=_sort_key(sort_by), reverse=True)

    return OrgReport(
        org=org,
        period_start=since,
        period_end=until,
        total_repos=len(repo_stats_list),
        total_commits=total_commits,
        total_additions=total_additions,
        total_deletions=total_deletions,
        total_open_prs=total_open_prs,
        total_merged_prs=total_merged_prs,
        total_open_issues=total_open_issues,
        languages=org_languages,
        contributors=org_contributors,
        repos=repo_stats_list,
        failed_repos=failed_repos,
    )
