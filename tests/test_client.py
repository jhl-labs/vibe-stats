"""Tests for the GitHub client module."""

from vibe_stats.github.client import GitHubClient


def test_client_instantiation():
    client = GitHubClient(token="test-token")
    assert client._client is not None
    assert "Bearer test-token" in client._client.headers["Authorization"]


def test_client_default_concurrency():
    client = GitHubClient(token="test-token", concurrency=10)
    assert client._semaphore._value == 10


def test_client_no_cache():
    client = GitHubClient(token="test-token", no_cache=True)
    assert client._cache is None


def test_client_cache_enabled_by_default():
    client = GitHubClient(token="test-token")
    assert client._cache is not None
