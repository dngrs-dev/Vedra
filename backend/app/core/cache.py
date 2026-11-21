"""Disk cache shared by both parts. Keys are namespaced; each part uses its own namespaces. Frozen after T0."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from diskcache import Cache

_cache = Cache(os.environ.get("CACHE_DIR", ".cache"), size_limit=2 * 1024**3)


def make_key(namespace: str, **parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str)
    return f"{namespace}:{hashlib.sha256(payload.encode()).hexdigest()}"


def get(key: str) -> Any | None:
    return _cache.get(key)


def set(key: str, value: Any, expire_s: float | None = None) -> None:  # noqa: A001
    _cache.set(key, value, expire=expire_s)
