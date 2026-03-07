from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from .config import settings


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, scope: str, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        if not settings.rate_limit_enabled:
            return True, 0
        now = time.monotonic()
        bucket_key = f"{scope}:{key}"
        with self._lock:
            bucket = self._buckets[bucket_key]
            edge = now - window_seconds
            while bucket and bucket[0] <= edge:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                return False, retry_after
            bucket.append(now)
            return True, 0


limiter = InMemoryRateLimiter()


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_http_rate_limit(
    request: Request,
    scope: str,
    limit: int,
    window_seconds: int = 60,
    key_suffix: str | None = None,
) -> None:
    key = get_client_ip(request)
    if key_suffix:
        key = f"{key}:{key_suffix}"
    allowed, retry_after = limiter.hit(scope, key, limit, window_seconds)
    if allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Rate limit exceeded. Retry in {retry_after}s",
        headers={"Retry-After": str(retry_after)},
    )
