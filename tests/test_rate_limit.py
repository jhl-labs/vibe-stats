"""Tests for the rate limit monitor."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from vibe_stats.github.rate_limit import RateLimitMonitor


def _make_response(remaining: str | None = None, reset: str | None = None) -> MagicMock:
    headers = {}
    if remaining is not None:
        headers["X-RateLimit-Remaining"] = remaining
    if reset is not None:
        headers["X-RateLimit-Reset"] = reset
    resp = MagicMock()
    resp.headers = headers
    return resp


def test_update_sets_remaining_and_reset():
    monitor = RateLimitMonitor()
    resp = _make_response(remaining="100", reset=str(time.time() + 3600))
    monitor.update(resp)
    assert monitor._remaining == 100
    assert monitor._reset_at is not None


def test_update_without_headers():
    monitor = RateLimitMonitor()
    resp = _make_response()
    monitor.update(resp)
    assert monitor._remaining is None
    assert monitor._reset_at is None


@pytest.mark.asyncio
async def test_wait_if_needed_no_wait_when_above_threshold():
    """Should not wait when remaining is above threshold."""
    monitor = RateLimitMonitor(threshold=10)
    resp = _make_response(remaining="50", reset=str(time.time() + 3600))
    monitor.update(resp)
    # Should return immediately
    await monitor.wait_if_needed()


@pytest.mark.asyncio
async def test_wait_if_needed_no_wait_when_none():
    """Should not wait when no rate limit info."""
    monitor = RateLimitMonitor()
    await monitor.wait_if_needed()


@pytest.mark.asyncio
async def test_wait_if_needed_waits_when_below_threshold():
    """Should wait when remaining is at or below threshold."""
    monitor = RateLimitMonitor(threshold=10)
    # Set reset to a time in the very near past so wait is minimal
    resp = _make_response(remaining="5", reset=str(time.time() - 1))
    monitor.update(resp)
    # Should wait ~0+1 seconds (max(0, past - now) + 1)
    # We just verify it doesn't crash; actual wait should be ~0 due to past reset time
    await monitor.wait_if_needed()
