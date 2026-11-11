import time
from collections import defaultdict, deque

from app.core.errors import RateLimited

_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def check_rate_limit(user_id: str, bucket: str, limit: int, window: float = 60.0) -> None:
    """In-memory sliding window per (user, bucket). Use Redis for multi-instance deployments."""
    now = time.monotonic()
    q = _hits[(user_id, bucket)]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise RateLimited(f"Rate limit exceeded ({limit} per minute). Try again shortly.")
    q.append(now)


def reset() -> None:
    _hits.clear()
