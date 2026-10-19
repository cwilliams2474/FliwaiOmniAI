"""Small in-process sliding-window limiter for sign-in attempts.

It is per backend process. The default deployment runs one process, which is enough
for brute-force protection; behind several workers each keeps its own window.
"""

import threading
import time
from collections import defaultdict, deque


class SlidingWindow:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, q: deque, now: float) -> None:
        while q and now - q[0] > self.window:
            q.popleft()

    def blocked(self, key: str) -> int:
        """Seconds until the key may try again, or 0 if not blocked."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            self._trim(q, now)
            if len(q) >= self.limit:
                return int(self.window - (now - q[0])) + 1
            return 0

    def hit(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)
