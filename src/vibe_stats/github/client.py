"""GitHub REST API client."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from ..cache import FileCache
from .rate_limit import RateLimitMonitor

BASE_URL = "https://api.github.com"


class GitHubClient:
    """Async GitHub REST API client with pagination and rate limit support."""

    def __init__(
        self, token: str, concurrency: int = 5, no_cache: bool = False
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers=headers,
            timeout=30.0,
        )
        self._rate_limit = RateLimitMonitor()
        self._semaphore = asyncio.Semaphore(concurrency)
        self._cache: FileCache | None = None if no_cache else FileCache()

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        async with self._semaphore:
            await self._rate_limit.wait_if_needed()
            response = await self._client.get(url, params=params)
            self._rate_limit.update(response)
            response.raise_for_status()
            return response

    async def _cached_get_json(
        self, url: str, params: dict[str, Any] | None = None
    ) -> Any:
        """GET with file cache support. Returns parsed JSON."""
        if self._cache is not None:
            cached = self._cache.get(url, params)
            if cached is not None:
                return cached
        response = await self._get(url, params)
        data = response.json()
        if self._cache is not None:
            self._cache.set(url, params, data)
        return data

    async def _cached_paginate(
        self, url: str, params: dict[str, Any] | None = None
    ) -> list[Any]:
        """Paginate with file cache support."""
        cache_params = dict(params or {})
        if self._cache is not None:
            cached = self._cache.get(url, cache_params)
            if cached is not None:
                return cached

        results = await self._paginate(url, params)
        if self._cache is not None:
            self._cache.set(url, cache_params, results)
        return results

    async def _paginate(self, url: str, params: dict[str, Any] | None = None) -> list[Any]:
        results: list[Any] = []
        params = dict(params or {})
        params.setdefault("per_page", 100)
        next_url: str | None = url

        while next_url is not None:
            response = await self._get(next_url, params)
            data = response.json()
            if isinstance(data, list):
                results.extend(data)
            else:
                results.append(data)

            # Follow Link header for next page
            next_url = None
            link_header = response.headers.get("Link", "")
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    next_url = part.split(";")[0].strip().strip("<>")
                    params = {}  # URL already contains params
                    break

        return results

    async def list_repos(
        self, org: str, include_forks: bool = False
    ) -> list[dict[str, Any]]:
        """List all repositories for an organization or user."""
        repo_type = "all" if include_forks else "sources"
        try:
            return await self._cached_paginate(
                f"/orgs/{org}/repos",
                params={"type": repo_type, "sort": "updated"},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return await self._cached_paginate(
                    f"/users/{org}/repos",
                    params={"type": repo_type, "sort": "updated"},
                )
            raise

    async def list_commits(
        self, owner: str, repo: str, since: str | None = None, until: str | None = None
    ) -> list[dict[str, Any]]:
        """List commits for a repository."""
        params: dict[str, Any] = {}
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        try:
            return await self._cached_paginate(
                f"/repos/{owner}/{repo}/commits", params=params
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 409:
                return []
            raise

    async def get_languages(self, owner: str, repo: str) -> dict[str, int]:
        """Get language breakdown (bytes) for a repository."""
        return await self._cached_get_json(f"/repos/{owner}/{repo}/languages")

    async def get_contributor_stats(
        self, owner: str, repo: str, retries: int = 3
    ) -> list[dict[str, Any]]:
        """Get contributor statistics. Handles 202 (computing) with retries."""
        url = f"/repos/{owner}/{repo}/stats/contributors"

        if self._cache is not None:
            cached = self._cache.get(url)
            if cached is not None:
                return cached

        for attempt in range(retries):
            try:
                response = await self._get(url)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 202 and attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            if response.status_code == 204:
                return []
            if response.status_code == 202 and attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            data = response.json()
            result = data if isinstance(data, list) else []
            if self._cache is not None:
                self._cache.set(url, None, result)
            return result
        return []

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        since: str | None = None,
        until: str | None = None,
    ) -> list[dict[str, Any]]:
        """List pull requests for a repository."""
        params: dict[str, Any] = {"state": state, "sort": "created", "direction": "desc"}
        results = await self._cached_paginate(
            f"/repos/{owner}/{repo}/pulls", params=params
        )
        # Filter by since/until on created_at
        if since or until:
            filtered = []
            for pr in results:
                created = pr.get("created_at", "")
                if since and created < since:
                    continue
                if until and created > until:
                    continue
                filtered.append(pr)
            return filtered
        return results

    async def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        """List issues (excluding pull requests) for a repository."""
        params: dict[str, Any] = {"state": state, "sort": "created", "direction": "desc"}
        if since:
            params["since"] = since
        results = await self._cached_paginate(
            f"/repos/{owner}/{repo}/issues", params=params
        )
        # GitHub issues API includes PRs; filter them out
        return [i for i in results if "pull_request" not in i]
