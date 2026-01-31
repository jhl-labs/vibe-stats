"""Tests for the cache module."""

from __future__ import annotations

import json
import time

from vibe_stats.cache import FileCache


def test_cache_get_set(tmp_path):
    cache = FileCache(cache_dir=tmp_path, ttl=3600)
    cache.set("/test/url", {"key": "val"}, [1, 2, 3])
    result = cache.get("/test/url", {"key": "val"})
    assert result == [1, 2, 3]


def test_cache_miss(tmp_path):
    cache = FileCache(cache_dir=tmp_path, ttl=3600)
    result = cache.get("/nonexistent", None)
    assert result is None


def test_cache_ttl_expired(tmp_path):
    cache = FileCache(cache_dir=tmp_path, ttl=1)
    cache.set("/test/url", None, {"data": True})

    # Manually backdate the timestamp
    key = FileCache._make_key("/test/url", None)
    path = tmp_path / f"{key}.json"
    data = json.loads(path.read_text())
    data["ts"] = time.time() - 10  # 10 seconds ago
    path.write_text(json.dumps(data))

    result = cache.get("/test/url", None)
    assert result is None


def test_cache_different_params(tmp_path):
    cache = FileCache(cache_dir=tmp_path, ttl=3600)
    cache.set("/url", {"a": "1"}, "first")
    cache.set("/url", {"a": "2"}, "second")
    assert cache.get("/url", {"a": "1"}) == "first"
    assert cache.get("/url", {"a": "2"}) == "second"


def test_cache_get_corrupted_json(tmp_path):
    """Should return None when cached file contains invalid JSON."""
    cache = FileCache(cache_dir=tmp_path, ttl=3600)
    cache.set("/test/url", None, "data")
    # Corrupt the file
    key = FileCache._make_key("/test/url", None)
    path = tmp_path / f"{key}.json"
    path.write_text("not valid json{{{")
    result = cache.get("/test/url", None)
    assert result is None


def test_cache_set_oserror(tmp_path):
    """Should not raise when write fails (e.g. read-only path)."""
    # Use a non-writable directory
    import os
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    cache = FileCache(cache_dir=readonly_dir, ttl=3600)
    os.chmod(readonly_dir, 0o444)
    try:
        # Should not raise
        cache.set("/test/url", None, "data")
    finally:
        os.chmod(readonly_dir, 0o755)
