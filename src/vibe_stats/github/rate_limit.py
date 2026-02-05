"""GitHub API rate limit monitoring."""

from __future__ import annotations

import asyncio
import time

import httpx


class RateLimitMonitor:
    """Monitors GitHub API rate limit from response headers."""

    def __init__(self, threshold: int = 10) -> None:
        self._remaining: int | None = None
        self._reset_at: float | None = None
        self._threshold = threshold

    def update(self, response: httpx.Response) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset_at = response.headers.get("X-RateLimit-Reset")
        if remaining is not None:
            self._remaining = int(remaining)
        if reset_at is not None:
            self._reset_at = float(reset_at)

    async def wait_if_needed(self) -> None:
        if (
            self._remaining is not None
            and self._remaining <= self._threshold
            and self._reset_at is not None
        ):
            wait_seconds = max(0, self._reset_at - time.time()) + 1
            if wait_seconds > 0:
                wait_seconds = min(wait_seconds, 3600)
                await asyncio.sleep(wait_seconds)
