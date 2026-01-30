"""File-based caching layer for API responses."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "vibe-stats"
DEFAULT_TTL = 3600  # 1 hour


class FileCache:
    """Simple file-based cache with TTL support."""

    def __init__(
        self, cache_dir: Path = DEFAULT_CACHE_DIR, ttl: int = DEFAULT_TTL
    ) -> None:
        self._cache_dir = cache_dir
        self._ttl = ttl
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _make_key(url: str, params: dict[str, Any] | None = None) -> str:
        raw = url + json.dumps(params or {}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _path_for(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    def get(self, url: str, params: dict[str, Any] | None = None) -> Any | None:
        key = self._make_key(url, params)
        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        if time.time() - data.get("ts", 0) > self._ttl:
            path.unlink(missing_ok=True)
            return None
        return data.get("value")

    def set(self, url: str, params: dict[str, Any] | None, value: Any) -> None:
        key = self._make_key(url, params)
        path = self._path_for(key)
        payload = {"ts": time.time(), "value": value}
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False))
        except OSError:
            pass
