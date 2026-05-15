"""Rate-limiting helpers."""

from __future__ import annotations

import time
from collections import deque
from threading import Lock

# In-process rolling window. Sufficient for single-process dev and small
# production. For multi-worker, swap with Redis (INCR + EXPIRE).
_BUCKETS: dict[str, deque] = {}
_LOCK = Lock()


def hit(scope: str, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Record a hit for ``scope:key``.

    Returns (allowed, retry_after_seconds). ``allowed=False`` means the
    request should be rejected.
    """
    bucket_key = f"{scope}::{key}"
    now = time.monotonic()
    cutoff = now - window_seconds
    with _LOCK:
        bucket = _BUCKETS.setdefault(bucket_key, deque())
        # Drop expired hits from the left.
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, int(window_seconds - (now - bucket[0])))
            return False, retry_after
        bucket.append(now)
        return True, 0


def reset(scope: str, key: str) -> None:
    bucket_key = f"{scope}::{key}"
    with _LOCK:
        _BUCKETS.pop(bucket_key, None)
