import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    """In-memory sliding window. Single-process only; use a shared store (e.g. Redis) when running several workers."""

    def __init__(self, clock=time.monotonic):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._clock = clock
        self._ops = 0

    def check(self, key: str, limit: int, window: float) -> tuple[bool, float]:
        now = self._clock()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= window:
                q.popleft()
            if len(q) >= limit:
                return False, window - (now - q[0])
            q.append(now)
            self._ops += 1
            if self._ops % 500 == 0:  # drop idle keys
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > 3600]:
                    del self._hits[k]
            return True, 0.0
