"""Tests for the GitHub client module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

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


@pytest.mark.asyncio
async def test_client_close():
    client = GitHubClient(token="test-token", no_cache=True)
    await client.close()


@pytest.mark.asyncio
async def test_client_context_manager():
    async with GitHubClient(token="test-token", no_cache=True) as client:
        assert client is not None


def _make_mock_response(
    status_code: int = 200,
    json_data=None,
    headers: dict | None = None,
):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else []
    resp.headers = headers or {"Link": ""}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


@pytest.mark.asyncio
async def test_get_basic():
    """_get should call httpx client and return response."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp = _make_mock_response(200, json_data={"key": "value"})
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client._get("/test")
    assert result == resp


@pytest.mark.asyncio
async def test_cached_get_json_with_cache_hit():
    """_cached_get_json should return cached data on hit."""
    client = GitHubClient(token="test-token")
    client._cache.get = MagicMock(return_value={"cached": True})

    result = await client._cached_get_json("/test", {"a": "1"})
    assert result == {"cached": True}


@pytest.mark.asyncio
async def test_cached_get_json_with_cache_miss():
    """_cached_get_json should fetch and cache on miss."""
    client = GitHubClient(token="test-token")
    client._cache.get = MagicMock(return_value=None)
    client._cache.set = MagicMock()
    resp = _make_mock_response(200, json_data={"fetched": True})
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client._cached_get_json("/test")
    assert result == {"fetched": True}
    client._cache.set.assert_called_once()


@pytest.mark.asyncio
async def test_cached_get_json_no_cache():
    """_cached_get_json should work without cache."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp = _make_mock_response(200, json_data={"data": 1})
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client._cached_get_json("/test")
    assert result == {"data": 1}


@pytest.mark.asyncio
async def test_cached_paginate_with_cache_hit():
    """_cached_paginate should return cached data on hit."""
    client = GitHubClient(token="test-token")
    client._cache.get = MagicMock(return_value=[{"name": "repo1"}])

    result = await client._cached_paginate("/test", {"a": "1"})
    assert result == [{"name": "repo1"}]


@pytest.mark.asyncio
async def test_cached_paginate_with_cache_miss():
    """_cached_paginate should paginate and cache on miss."""
    client = GitHubClient(token="test-token")
    client._cache.get = MagicMock(return_value=None)
    client._cache.set = MagicMock()
    resp = _make_mock_response(200, json_data=[{"name": "repo1"}])
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client._cached_paginate("/test")
    assert result == [{"name": "repo1"}]
    client._cache.set.assert_called_once()


@pytest.mark.asyncio
async def test_paginate_single_page():
    """_paginate should handle a single page response."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp = _make_mock_response(200, json_data=[{"id": 1}, {"id": 2}])
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client._paginate("/test")
    assert result == [{"id": 1}, {"id": 2}]


@pytest.mark.asyncio
async def test_paginate_multiple_pages():
    """_paginate should follow Link headers for pagination."""
    client = GitHubClient(token="test-token", no_cache=True)

    resp1 = _make_mock_response(
        200,
        json_data=[{"id": 1}],
        headers={"Link": '<https://api.github.com/test?page=2>; rel="next"'},
    )
    resp2 = _make_mock_response(200, json_data=[{"id": 2}])

    client._client.get = AsyncMock(side_effect=[resp1, resp2])
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client._paginate("/test")
    assert result == [{"id": 1}, {"id": 2}]


@pytest.mark.asyncio
async def test_paginate_non_list_response():
    """_paginate should handle non-list (object) responses."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp = _make_mock_response(200, json_data={"total": 5})
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client._paginate("/test")
    assert result == [{"total": 5}]


@pytest.mark.asyncio
async def test_list_repos_org():
    """list_repos should call org endpoint."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp = _make_mock_response(200, json_data=[{"name": "repo1"}])
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client.list_repos("myorg")
    assert result == [{"name": "repo1"}]


@pytest.mark.asyncio
async def test_list_repos_fallback_to_user():
    """list_repos should fall back to user endpoint on 404."""
    client = GitHubClient(token="test-token", no_cache=True)

    # First call: 404 for org
    resp_404 = _make_mock_response(404)
    # Second call: success for user
    resp_ok = _make_mock_response(200, json_data=[{"name": "repo1"}])

    call_count = 0

    async def mock_get(url, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.HTTPStatusError("404", request=MagicMock(), response=resp_404)
        return resp_ok

    client._client.get = mock_get
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client.list_repos("myuser")
    assert result == [{"name": "repo1"}]


@pytest.mark.asyncio
async def test_list_repos_include_forks():
    """list_repos should use 'all' type when include_forks=True."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp = _make_mock_response(200, json_data=[])
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    await client.list_repos("myorg", include_forks=True)
    call_args = client._client.get.call_args
    params = call_args.kwargs.get("params") or call_args[1].get("params", {})
    assert params.get("type") == "all"


@pytest.mark.asyncio
async def test_list_commits_basic():
    """list_commits should return commits."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp = _make_mock_response(200, json_data=[{"sha": "abc"}])
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client.list_commits("owner", "repo")
    assert result == [{"sha": "abc"}]


@pytest.mark.asyncio
async def test_list_commits_with_since_until():
    """list_commits should pass since/until params."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp = _make_mock_response(200, json_data=[])
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    await client.list_commits("o", "r", since="2024-01-01T00:00:00Z", until="2024-12-31T23:59:59Z")
    call_args = client._client.get.call_args
    params = call_args.kwargs.get("params") or call_args[1].get("params", {})
    assert params.get("since") == "2024-01-01T00:00:00Z"
    assert params.get("until") == "2024-12-31T23:59:59Z"


@pytest.mark.asyncio
async def test_list_commits_409_empty_repo():
    """list_commits should return [] on 409 (empty repo)."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp_409 = _make_mock_response(409)

    async def mock_get(url, params=None):
        raise httpx.HTTPStatusError("409", request=MagicMock(), response=resp_409)

    client._client.get = mock_get
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client.list_commits("owner", "repo")
    assert result == []


@pytest.mark.asyncio
async def test_get_languages():
    """get_languages should return language dict."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp = _make_mock_response(200, json_data={"Python": 5000})
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client.get_languages("owner", "repo")
    assert result == {"Python": 5000}


@pytest.mark.asyncio
async def test_get_contributor_stats_success():
    """get_contributor_stats should return contributor list."""
    client = GitHubClient(token="test-token", no_cache=True)
    data = [{"author": {"login": "alice"}, "total": 10, "weeks": []}]
    resp = _make_mock_response(200, json_data=data)
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client.get_contributor_stats("owner", "repo")
    assert result == data


@pytest.mark.asyncio
async def test_get_contributor_stats_204():
    """get_contributor_stats should return [] on 204."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp = _make_mock_response(204)
    resp.raise_for_status = MagicMock()  # 204 doesn't raise
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client.get_contributor_stats("owner", "repo")
    assert result == []


@pytest.mark.asyncio
async def test_get_contributor_stats_202_retry():
    """get_contributor_stats should retry on 202."""
    client = GitHubClient(token="test-token", no_cache=True)
    data = [{"author": {"login": "alice"}, "total": 10, "weeks": []}]

    resp_202 = _make_mock_response(202)
    resp_202.raise_for_status = MagicMock()
    resp_202.json.return_value = None

    resp_200 = _make_mock_response(200, json_data=data)

    client._client.get = AsyncMock(side_effect=[resp_202, resp_200])
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    with patch("vibe_stats.github.client.asyncio.sleep", new_callable=AsyncMock):
        result = await client.get_contributor_stats("owner", "repo", retries=3)
    assert result == data


@pytest.mark.asyncio
async def test_get_contributor_stats_202_exhaust_retries():
    """get_contributor_stats should return [] when all retries exhausted."""
    client = GitHubClient(token="test-token", no_cache=True)

    resp_202 = _make_mock_response(202)
    resp_202.raise_for_status = MagicMock()
    resp_202.json.return_value = None

    client._client.get = AsyncMock(return_value=resp_202)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    with patch("vibe_stats.github.client.asyncio.sleep", new_callable=AsyncMock):
        result = await client.get_contributor_stats("owner", "repo", retries=2)
    assert result == []


@pytest.mark.asyncio
async def test_get_contributor_stats_202_http_error_retry():
    """get_contributor_stats should retry on HTTPStatusError with 202."""
    client = GitHubClient(token="test-token", no_cache=True)
    data = [{"author": {"login": "alice"}}]

    resp_202 = _make_mock_response(202)
    resp_200 = _make_mock_response(200, json_data=data)

    call_count = 0

    async def mock_get(url, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.HTTPStatusError("202", request=MagicMock(), response=resp_202)
        return resp_200

    client._client.get = mock_get
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    with patch("vibe_stats.github.client.asyncio.sleep", new_callable=AsyncMock):
        result = await client.get_contributor_stats("owner", "repo", retries=3)
    assert result == data


@pytest.mark.asyncio
async def test_get_contributor_stats_non_list_response():
    """get_contributor_stats should return [] for non-list json response."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp = _make_mock_response(200, json_data={"error": "not a list"})
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client.get_contributor_stats("owner", "repo")
    assert result == []


@pytest.mark.asyncio
async def test_get_contributor_stats_cache_hit():
    """get_contributor_stats should return cached data."""
    client = GitHubClient(token="test-token")
    cached = [{"author": {"login": "cached"}}]
    client._cache.get = MagicMock(return_value=cached)

    result = await client.get_contributor_stats("owner", "repo")
    assert result == cached


@pytest.mark.asyncio
async def test_get_contributor_stats_cache_set():
    """get_contributor_stats should cache the result."""
    client = GitHubClient(token="test-token")
    data = [{"author": {"login": "alice"}}]
    client._cache.get = MagicMock(return_value=None)
    client._cache.set = MagicMock()
    resp = _make_mock_response(200, json_data=data)
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client.get_contributor_stats("owner", "repo")
    assert result == data
    client._cache.set.assert_called_once()


@pytest.mark.asyncio
async def test_list_pull_requests_basic():
    """list_pull_requests should return PRs."""
    client = GitHubClient(token="test-token", no_cache=True)
    prs = [{"state": "open", "created_at": "2024-06-01T00:00:00Z"}]
    resp = _make_mock_response(200, json_data=prs)
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client.list_pull_requests("owner", "repo")
    assert result == prs


@pytest.mark.asyncio
async def test_list_pull_requests_with_since_until():
    """list_pull_requests should filter by since/until."""
    client = GitHubClient(token="test-token", no_cache=True)
    prs = [
        {"state": "open", "created_at": "2024-01-01T00:00:00Z"},
        {"state": "open", "created_at": "2024-06-01T00:00:00Z"},
        {"state": "open", "created_at": "2024-12-01T00:00:00Z"},
    ]
    resp = _make_mock_response(200, json_data=prs)
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client.list_pull_requests(
        "owner", "repo", since="2024-03-01T00:00:00Z", until="2024-09-01T00:00:00Z"
    )
    assert len(result) == 1
    assert result[0]["created_at"] == "2024-06-01T00:00:00Z"


@pytest.mark.asyncio
async def test_list_issues_basic():
    """list_issues should return issues excluding PRs."""
    client = GitHubClient(token="test-token", no_cache=True)
    issues = [
        {"state": "open", "title": "Bug"},
        {"state": "open", "title": "Feature", "pull_request": {"url": "..."}},
    ]
    resp = _make_mock_response(200, json_data=issues)
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    result = await client.list_issues("owner", "repo")
    assert len(result) == 1
    assert result[0]["title"] == "Bug"


@pytest.mark.asyncio
async def test_list_issues_with_since():
    """list_issues should pass since param."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp = _make_mock_response(200, json_data=[])
    client._client.get = AsyncMock(return_value=resp)
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    await client.list_issues("o", "r", since="2024-01-01T00:00:00Z")
    call_args = client._client.get.call_args
    params = call_args.kwargs.get("params") or call_args[1].get("params", {})
    assert params.get("since") == "2024-01-01T00:00:00Z"


@pytest.mark.asyncio
async def test_list_repos_non_404_error():
    """list_repos should re-raise non-404 errors."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp_500 = _make_mock_response(500)

    async def mock_get(url, params=None):
        raise httpx.HTTPStatusError("500", request=MagicMock(), response=resp_500)

    client._client.get = mock_get
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    with pytest.raises(httpx.HTTPStatusError):
        await client.list_repos("myorg")


@pytest.mark.asyncio
async def test_list_commits_non_409_error():
    """list_commits should re-raise non-409 errors."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp_500 = _make_mock_response(500)

    async def mock_get(url, params=None):
        raise httpx.HTTPStatusError("500", request=MagicMock(), response=resp_500)

    client._client.get = mock_get
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    with pytest.raises(httpx.HTTPStatusError):
        await client.list_commits("owner", "repo")


@pytest.mark.asyncio
async def test_get_contributor_stats_non_202_http_error():
    """get_contributor_stats should raise on non-202 HTTP errors."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp_500 = _make_mock_response(500)

    async def mock_get(url, params=None):
        raise httpx.HTTPStatusError("500", request=MagicMock(), response=resp_500)

    client._client.get = mock_get
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_contributor_stats("owner", "repo")


@pytest.mark.asyncio
async def test_get_contributor_stats_202_last_attempt_raises():
    """get_contributor_stats should raise on 202 HTTPStatusError on last retry."""
    client = GitHubClient(token="test-token", no_cache=True)
    resp_202 = _make_mock_response(202)

    async def mock_get(url, params=None):
        raise httpx.HTTPStatusError("202", request=MagicMock(), response=resp_202)

    client._client.get = mock_get
    client._rate_limit.wait_if_needed = AsyncMock()
    client._rate_limit.update = MagicMock()

    with patch("vibe_stats.github.client.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_contributor_stats("owner", "repo", retries=1)


@pytest.mark.asyncio
async def test_get_contributor_stats_zero_retries():
    """get_contributor_stats should return [] when retries=0."""
    client = GitHubClient(token="test-token", no_cache=True)
    result = await client.get_contributor_stats("owner", "repo", retries=0)
    assert result == []
