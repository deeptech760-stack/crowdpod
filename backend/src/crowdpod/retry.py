# Adapted from the upstream project listed in NOTICE (AGPL-3.0); modified 2026-10-30.
"""Async retry with exponential backoff for calls to external services."""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger("crowdpod.retry")

T = TypeVar("T")


def retry_with_backoff_async(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    on_retry: Callable[[BaseException, int], None] | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = initial_delay
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        logger.error("%s failed after %d retries: %s", func.__name__, max_retries, e)
                        raise
                    current_delay = min(delay, max_delay)
                    if jitter:
                        current_delay *= 0.5 + random.random()
                    logger.warning(
                        "%s attempt %d failed: %s; retrying in %.1fs", func.__name__, attempt + 1, e, current_delay
                    )
                    if on_retry:
                        on_retry(e, attempt + 1)
                    await asyncio.sleep(current_delay)
                    delay *= backoff_factor
            raise AssertionError("unreachable")

        return wrapper

    return decorator
