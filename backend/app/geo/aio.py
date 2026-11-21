"""Waiting on shared background tasks without cancelling them."""
from __future__ import annotations

import asyncio
from typing import TypeVar

T = TypeVar("T")


async def wait_shared(task: asyncio.Task[T], timeout: float) -> T:
    """Result of a shared background task, or asyncio.TimeoutError after `timeout` s; the task keeps running.

    Unlike wait_for(shield(task)), a late failure of the task is not logged as "exception in shielded future"
    (its exception is consumed by the task's own done-callback)."""
    done, _ = await asyncio.wait({task}, timeout=max(timeout, 0.0))
    if not done:
        raise asyncio.TimeoutError
    return task.result()
