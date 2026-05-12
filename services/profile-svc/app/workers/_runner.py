"""Sync-to-async bridge for Celery tasks."""

from __future__ import annotations

import asyncio
from typing import Any, Coroutine


def run_sync(coro: Coroutine) -> Any:
    """Run an async coroutine from a synchronous Celery task."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)
