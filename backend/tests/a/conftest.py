"""Part A test setup: make `app` and `scripts` importable when running `pytest tests/a` from backend/,
isolate the disk cache and the shared HTTP client per test."""
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
# app.core.cache opens its directory at import time: never touch the developer's .cache from tests.
os.environ.setdefault("CACHE_DIR", tempfile.mkdtemp(prefix="vedra-test-cache-"))

import pytest  # noqa: E402

DATA = Path(__file__).parent / "data"


@pytest.fixture(autouse=True)
def _isolated_io(monkeypatch):
    """No cache hits between tests, fresh httpx client per test (event loops differ)."""
    from app.core import cache, http

    monkeypatch.setattr(cache, "get", lambda key: None)
    monkeypatch.setattr(cache, "set", lambda key, value, expire_s=None: None)
    monkeypatch.setattr(http, "_client", None)
    yield
