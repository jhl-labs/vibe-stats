"""Data aggregation: collect per-repo stats and produce an OrgReport."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone

from rich.progress import Progress, SpinnerColumn, TextColumn

from .github.client import GitHubClient
from .models import (
    CommitPatternStats,
    ContributorStats,
    ContributorTrend,
    IssueInsights,
    LanguageStats,
    OrgReport,
    PRInsights,
    RepoStats,
)

logger = logging.getLogger(__name__)

KNOWN_BOTS = frozenset(
    {
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
    }
)


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


_CONVENTIONAL_TYPES = {"feat", "fix", "refactor", "docs", "test", "chore", "style", "ci"}

_WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _analyze_commit_patterns(commits: list[dict]) -> CommitPatternStats:
    """Analyze conventional commit types and temporal distribution."""
    import re

    pattern = re.compile(r"^(\w+)[\(:\!]")
    counts: dict[str, int] = {t: 0 for t in _CONVENTIONAL_TYPES}
    counts["other"] = 0
    hourly: dict[int, int] = {}
    weekday: dict[int, int] = {}

    for commit in commits:
        # Parse commit type from message
        msg = ""
        commit_data = commit.get("commit", {})
        if isinstance(commit_data, dict):
            msg = commit_data.get("message", "")
        m = pattern.match(msg)
        if m:
            ctype = m.group(1).lower()
            if ctype in _CONVENTIONAL_TYPES:
                counts[ctype] += 1
            else:
                counts["other"] += 1
        else:
            counts["other"] += 1

        # Parse date for temporal distribution
        author_data = commit_data.get("author", {}) if isinstance(commit_data, dict) else {}
        date_str = author_data.get("date", "") if isinstance(author_data, dict) else ""
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                hour = dt.hour
                hourly[hour] = hourly.get(hour, 0) + 1
                wd = dt.weekday()  # 0=Mon
                weekday[wd] = weekday.get(wd, 0) + 1
            except (ValueError, AttributeError):
                pass

    return CommitPatternStats(
        feat=counts["feat"],
        fix=counts["fix"],
        refactor=counts["refactor"],
        docs=counts["docs"],
        test=counts["test"],
        chore=counts["chore"],
        style=counts["style"],
        ci=counts["ci"],
        other=counts["other"],
        total=len(commits),
        hourly_distribution=hourly,
        weekday_distribution=weekday,
    )


def _analyze_pr_insights(prs: list[dict]) -> PRInsights:
    """Analyze PR merge/close times and author stats."""
    merge_hours: list[float] = []
    close_hours: list[float] = []
    draft_count = 0
    author_counts: dict[str, int] = {}

    for pr in prs:
        # Draft count
        if pr.get("draft"):
            draft_count += 1

        # Author stats
        user = pr.get("user", {})
        if isinstance(user, dict):
            login = user.get("login", "")
            if login:
                author_counts[login] = author_counts.get(login, 0) + 1

        created = pr.get("created_at", "")
        if not created:
            continue

        try:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        # Merge time
        merged = pr.get("merged_at", "")
        if merged:
            try:
                merged_dt = datetime.fromisoformat(merged.replace("Z", "+00:00"))
                hours = (merged_dt - created_dt).total_seconds() / 3600
                if hours >= 0:
                    merge_hours.append(hours)
            except (ValueError, AttributeError):
                pass

        # Close time (for non-merged closed PRs)
        closed = pr.get("closed_at", "")
        if closed and not merged:
            try:
                closed_dt = datetime.fromisoformat(closed.replace("Z", "+00:00"))
                hours = (closed_dt - created_dt).total_seconds() / 3600
                if hours >= 0:
                    close_hours.append(hours)
            except (ValueError, AttributeError):
                pass

    avg_merge = round(sum(merge_hours) / len(merge_hours), 1) if merge_hours else None
    median_merge = None
    if merge_hours:
        sorted_h = sorted(merge_hours)
        mid = len(sorted_h) // 2
        median_merge = round(
            (sorted_h[mid] + sorted_h[mid - 1]) / 2 if len(sorted_h) % 2 == 0 else sorted_h[mid],
            1,
        )
    avg_close = round(sum(close_hours) / len(close_hours), 1) if close_hours else None

    top_authors = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return PRInsights(
        total_analyzed=len(prs),
        avg_merge_hours=avg_merge,
        median_merge_hours=median_merge,
        avg_close_hours=avg_close,
        draft_count=draft_count,
        top_authors=top_authors,
    )


def _analyze_issue_insights(issues: list[dict]) -> IssueInsights:
    """Analyze issue label distribution and reporter stats."""
    label_counts: dict[str, int] = {}
    reporter_counts: dict[str, int] = {}

    for issue in issues:
        # Labels
        labels = issue.get("labels", [])
        if isinstance(labels, list):
            for label in labels:
                name = label.get("name", "") if isinstance(label, dict) else str(label)
                if name:
                    label_counts[name] = label_counts.get(name, 0) + 1

        # Reporter
        user = issue.get("user", {})
        if isinstance(user, dict):
            login = user.get("login", "")
            if login:
                reporter_counts[login] = reporter_counts.get(login, 0) + 1

    top_reporters = sorted(reporter_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return IssueInsights(
        total_analyzed=len(issues),
        label_distribution=label_counts,
        top_reporters=top_reporters,
    )


def _analyze_contributor_trends(
    raw_contributors: list[dict],
    since_ts: float | None = None,
    until_ts: float | None = None,
) -> list[ContributorTrend]:
    """Analyze contributor activity timelines."""
    trends: list[ContributorTrend] = []

    for c in raw_contributors:
        author = c.get("author")
        if not author:
            continue
        login = author.get("login", "unknown")
        weeks = c.get("weeks", [])

        active_week_timestamps: list[int] = []
        for w in weeks:
            week_start = w.get("w", 0)
            if since_ts is not None and week_start + 7 * 86400 <= since_ts:
                continue
            if until_ts is not None and week_start > until_ts:
                continue
            if w.get("c", 0) > 0 or w.get("a", 0) > 0 or w.get("d", 0) > 0:
                active_week_timestamps.append(week_start)

        if not active_week_timestamps:
            continue

        first_ts = min(active_week_timestamps)
        last_ts = max(active_week_timestamps)
        first_dt = datetime.fromtimestamp(first_ts, tz=timezone.utc)
        last_dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
        total_span_weeks = max(1, (last_ts - first_ts) // (7 * 86400) + 1)

        trends.append(
            ContributorTrend(
                username=login,
                first_active_week=first_dt.strftime("%Y-%m-%d"),
                last_active_week=last_dt.strftime("%Y-%m-%d"),
                active_weeks=len(active_week_timestamps),
                total_weeks=total_span_weeks,
            )
        )

    trends.sort(key=lambda t: t.active_weeks, reverse=True)
    return trends


async def _collect_repo_stats(
    client: GitHubClient,
    owner: str,
    repo_name: str,
    since: str | None = None,
    until: str | None = None,
    repo_meta: dict | None = None,
) -> RepoStats:
    """Collect stats for a single repository."""
    commits_task = asyncio.create_task(
        client.list_commits(owner, repo_name, since=since, until=until)
    )
    languages_task = asyncio.create_task(client.get_languages(owner, repo_name))
    contributors_task = asyncio.create_task(
        client.get_contributor_stats(owner, repo_name)
    )
    prs_task = asyncio.create_task(
        client.list_pull_requests(
            owner, repo_name, state="all", since=since, until=until
        )
    )
    issues_task = asyncio.create_task(
        client.list_issues(owner, repo_name, state="open", since=since)
    )

    results = await asyncio.gather(
        commits_task,
        languages_task,
        contributors_task,
        prs_task,
        issues_task,
        return_exceptions=True,
    )
    commits, lang_bytes, raw_contributors, prs, issues = results

    def _warn(api_name: str, exc: Exception) -> None:
        # Extract just the status code + reason, not the full URL
        msg = str(exc)
        if "HTTPStatusError" in type(exc).__name__ or "HTTP" in type(exc).__name__:
            # e.g. "Client error '404 Not Found' for url ..." -> "404 Not Found"
            import re as _re
            m = _re.search(r"'(\d+ [^']+)'", msg)
            msg = m.group(1) if m else msg
        logger.warning("%s/%s %s: %s", owner, repo_name, api_name, msg)

    if isinstance(commits, Exception):
        _warn("commits", commits)
        commits = []
    if isinstance(lang_bytes, Exception):
        _warn("languages", lang_bytes)
        lang_bytes = {}
    if isinstance(raw_contributors, Exception):
        _warn("contributors", raw_contributors)
        raw_contributors = []
    if isinstance(prs, Exception):
        _warn("pulls", prs)
        prs = []
    if isinstance(issues, Exception):
        _warn("issues", issues)
        issues = []

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
            languages.append(
                LanguageStats(
                    language=lang,
                    bytes=b,
                    percentage=round(b / total_bytes * 100, 1) if total_bytes else 0,
                )
            )

    # Contributors — filter weeks by since/until when provided
    since_ts: float | None = None
    until_ts: float | None = None
    if since:
        try:
            since_ts = datetime.fromisoformat(since.replace("Z", "+00:00")).timestamp()
        except Exception:
            pass
    if until:
        try:
            until_ts = datetime.fromisoformat(until.replace("Z", "+00:00")).timestamp()
        except Exception:
            pass

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
            contributors.append(
                ContributorStats(
                    username=author.get("login", "unknown"),
                    commits=commits_count,
                    additions=additions,
                    deletions=deletions,
                )
            )
        contributors.sort(key=lambda x: x.commits, reverse=True)

    # New insight analyses
    commit_patterns = _analyze_commit_patterns(commits) if isinstance(commits, list) else None
    pr_insights = _analyze_pr_insights(prs) if isinstance(prs, list) else None
    issue_insights = _analyze_issue_insights(issues) if isinstance(issues, list) else None
    contributor_trends = (
        _analyze_contributor_trends(raw_contributors, since_ts, until_ts)
        if isinstance(raw_contributors, list)
        else []
    )

    # Extract metadata from repo dict (list_repos response)
    meta = repo_meta or {}

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
        stars=meta.get("stargazers_count", 0),
        forks=meta.get("forks_count", 0),
        size_kb=meta.get("size", 0),
        is_archived=meta.get("archived", False),
        primary_language=meta.get("language"),
        description=meta.get("description"),
        created_at=meta.get("created_at"),
        pushed_at=meta.get("pushed_at"),
        visibility=meta.get("visibility"),
        commit_patterns=commit_patterns,
        pr_insights=pr_insights,
        issue_insights=issue_insights,
        contributor_trends=contributor_trends,
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
        task = progress.add_task(
            f"Collecting stats for {len(repos)} repos...", total=len(repos)
        )

        async def collect_and_update(repo: dict) -> RepoStats | None:
            name = repo["name"]
            try:
                stats = await _collect_repo_stats(
                    client, org, name, since=since, until=until,
                    repo_meta=repo,
                )
                return stats
            except Exception:
                logger.warning("Failed to collect stats for %s/%s", org, name)
                failed_repos.append(name)
                return None
            finally:
                progress.advance(task)

        results = await asyncio.gather(*(collect_and_update(r) for r in repos))
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

    # Aggregate new org-level insights
    total_stars = sum(r.stars for r in repo_stats_list)
    total_forks = sum(r.forks for r in repo_stats_list)
    archived_repos = sum(1 for r in repo_stats_list if r.is_archived)

    # Merge commit patterns across repos
    org_commit_patterns: CommitPatternStats | None = None
    all_patterns = [r.commit_patterns for r in repo_stats_list if r.commit_patterns]
    if all_patterns:
        merged_hourly: dict[int, int] = {}
        merged_weekday: dict[int, int] = {}
        for p in all_patterns:
            for h, cnt in p.hourly_distribution.items():
                merged_hourly[h] = merged_hourly.get(h, 0) + cnt
            for d, cnt in p.weekday_distribution.items():
                merged_weekday[d] = merged_weekday.get(d, 0) + cnt
        org_commit_patterns = CommitPatternStats(
            feat=sum(p.feat for p in all_patterns),
            fix=sum(p.fix for p in all_patterns),
            refactor=sum(p.refactor for p in all_patterns),
            docs=sum(p.docs for p in all_patterns),
            test=sum(p.test for p in all_patterns),
            chore=sum(p.chore for p in all_patterns),
            style=sum(p.style for p in all_patterns),
            ci=sum(p.ci for p in all_patterns),
            other=sum(p.other for p in all_patterns),
            total=sum(p.total for p in all_patterns),
            hourly_distribution=merged_hourly,
            weekday_distribution=merged_weekday,
        )

    # Merge PR insights across repos
    org_pr_insights: PRInsights | None = None
    all_pr = [r.pr_insights for r in repo_stats_list if r.pr_insights]
    if all_pr:
        total_draft = 0
        author_totals: dict[str, int] = {}
        total_pr_analyzed = 0
        merge_weighted: list[tuple[float, int]] = []
        close_weighted: list[tuple[float, int]] = []
        for pi in all_pr:
            total_pr_analyzed += pi.total_analyzed
            total_draft += pi.draft_count
            for author, cnt in pi.top_authors:
                author_totals[author] = author_totals.get(author, 0) + cnt
            if pi.avg_merge_hours is not None:
                merge_weighted.append((pi.avg_merge_hours, pi.total_analyzed))
            if pi.avg_close_hours is not None:
                close_weighted.append((pi.avg_close_hours, pi.total_analyzed))
        total_merge_w = sum(w for _, w in merge_weighted)
        total_close_w = sum(w for _, w in close_weighted)
        org_avg_merge = (
            round(sum(h * w for h, w in merge_weighted) / total_merge_w, 1)
            if total_merge_w > 0
            else None
        )
        org_avg_close = (
            round(sum(h * w for h, w in close_weighted) / total_close_w, 1)
            if total_close_w > 0
            else None
        )
        org_top_authors = sorted(author_totals.items(), key=lambda x: x[1], reverse=True)[:10]
        org_pr_insights = PRInsights(
            total_analyzed=total_pr_analyzed,
            avg_merge_hours=org_avg_merge,
            median_merge_hours=None,  # Can't compute org-level median from per-repo medians
            avg_close_hours=org_avg_close,
            draft_count=total_draft,
            top_authors=org_top_authors,
        )

    # Merge issue insights across repos
    org_issue_insights: IssueInsights | None = None
    all_issues = [r.issue_insights for r in repo_stats_list if r.issue_insights]
    if all_issues:
        merged_labels: dict[str, int] = {}
        merged_reporters: dict[str, int] = {}
        total_issue_analyzed = 0
        for ii in all_issues:
            total_issue_analyzed += ii.total_analyzed
            for label, cnt in ii.label_distribution.items():
                merged_labels[label] = merged_labels.get(label, 0) + cnt
            for reporter, cnt in ii.top_reporters:
                merged_reporters[reporter] = merged_reporters.get(reporter, 0) + cnt
        org_issue_insights = IssueInsights(
            total_analyzed=total_issue_analyzed,
            label_distribution=merged_labels,
            top_reporters=sorted(merged_reporters.items(), key=lambda x: x[1], reverse=True)[:10],
        )

    # Merge contributor trends across repos
    org_trend_map: dict[str, ContributorTrend] = {}
    for r in repo_stats_list:
        for t in r.contributor_trends:
            if t.username in org_trend_map:
                existing = org_trend_map[t.username]
                first = min(existing.first_active_week, t.first_active_week)
                last = max(existing.last_active_week, t.last_active_week)
                # Recalculate total_weeks from merged date span
                try:
                    first_dt = datetime.strptime(first, "%Y-%m-%d")
                    last_dt = datetime.strptime(last, "%Y-%m-%d")
                    span_weeks = max(1, (last_dt - first_dt).days // 7 + 1)
                except ValueError:
                    span_weeks = max(existing.total_weeks, t.total_weeks)
                # Sum active_weeks but cap at total span
                merged_active = existing.active_weeks + t.active_weeks
                org_trend_map[t.username] = ContributorTrend(
                    username=t.username,
                    first_active_week=first,
                    last_active_week=last,
                    active_weeks=min(merged_active, span_weeks),
                    total_weeks=span_weeks,
                )
            else:
                org_trend_map[t.username] = ContributorTrend(
                    username=t.username,
                    first_active_week=t.first_active_week,
                    last_active_week=t.last_active_week,
                    active_weeks=t.active_weeks,
                    total_weeks=t.total_weeks,
                )
    # Apply same filters as contributors
    filtered_usernames: set[str] | None = None
    if exclude_bots or min_commits > 0:
        filtered_usernames = {c.username for c in org_contributors}
    if filtered_usernames is not None:
        org_trend_map = {k: v for k, v in org_trend_map.items() if k in filtered_usernames}

    org_contributor_trends = sorted(
        org_trend_map.values(), key=lambda t: t.active_weeks, reverse=True
    )

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
        total_stars=total_stars,
        total_forks=total_forks,
        archived_repos=archived_repos,
        commit_patterns=org_commit_patterns,
        pr_insights=org_pr_insights,
        issue_insights=org_issue_insights,
        contributor_trends=org_contributor_trends,
    )
