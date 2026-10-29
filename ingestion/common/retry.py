"""Retry dengan exponential backoff + full jitter (untuk error sementara: koneksi, timeout)."""
from __future__ import annotations

import functools
import logging
import random
import time

log = logging.getLogger(__name__)


def retry(exceptions: tuple[type[BaseException], ...], attempts: int = 4, base_delay: float = 2.0,
          max_delay: float = 30.0, sleep=time.sleep):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    if attempt == attempts:
                        raise
                    delay = random.uniform(0, min(max_delay, base_delay * 2 ** (attempt - 1)))
                    log.warning("%s gagal (percobaan %d/%d): %s; ulang dalam %.1fs",
                                fn.__name__, attempt, attempts, exc, delay)
                    sleep(delay)
        return wrapper
    return decorator
