"""Simple retry with exponential backoff — no external dependencies.

Usage:
    from src.common.retry import retry

    @retry(max_attempts=3, base_delay=1.0, exceptions=(requests.RequestException,))
    def fetch_data():
        return requests.get(url, timeout=10)

    # Async version:
    @retry(max_attempts=3, base_delay=1.0, exceptions=(requests.RequestException,))
    async def fetch_data_async():
        ...
"""
import asyncio
import functools
import logging
import time

logger = logging.getLogger(__name__)


def retry(max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 30.0,
          exceptions: tuple = (Exception,), on_retry=None):
    """Decorator that retries a function with exponential backoff.

    Works with both sync and async functions.
    """
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt == max_attempts:
                        break
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    logger.warning("%s attempt %d/%d failed: %s — retrying in %.1fs",
                                   func.__name__, attempt, max_attempts, e, delay)
                    if on_retry:
                        on_retry(attempt, e)
                    await asyncio.sleep(delay)
            raise last_exc

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt == max_attempts:
                        break
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    logger.warning("%s attempt %d/%d failed: %s — retrying in %.1fs",
                                   func.__name__, attempt, max_attempts, e, delay)
                    if on_retry:
                        on_retry(attempt, e)
                    time.sleep(delay)
            raise last_exc

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator
