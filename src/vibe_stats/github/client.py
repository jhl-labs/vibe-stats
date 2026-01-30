"""GitHub REST API client."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .rate_limit import RateLimitMonitor

BASE_URL = "https://api.github.com"


class GitHubClient:
    """Async GitHub REST API client with pagination and rate limit support."""

    def __init__(self, token: str, concurrency: int = 5) -> None:
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

    async def list_repos(self, org: str) -> list[dict[str, Any]]:
        """List all repositories for an organization."""
        return await self._paginate(
            f"/orgs/{org}/repos",
            params={"type": "sources", "sort": "updated"},
        )

    async def list_commits(
        self, owner: str, repo: str, since: str | None = None, until: str | None = None
    ) -> list[dict[str, Any]]:
        """List commits for a repository."""
        params: dict[str, Any] = {}
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        return await self._paginate(f"/repos/{owner}/{repo}/commits", params=params)

    async def get_languages(self, owner: str, repo: str) -> dict[str, int]:
        """Get language breakdown (bytes) for a repository."""
        response = await self._get(f"/repos/{owner}/{repo}/languages")
        return response.json()

    async def get_contributor_stats(
        self, owner: str, repo: str, retries: int = 3
    ) -> list[dict[str, Any]]:
        """Get contributor statistics. Handles 202 (computing) with retries."""
        for attempt in range(retries):
            try:
                response = await self._get(f"/repos/{owner}/{repo}/stats/contributors")
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 202 and attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            if response.status_code == 202 and attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            data = response.json()
            return data if isinstance(data, list) else []
        return []
