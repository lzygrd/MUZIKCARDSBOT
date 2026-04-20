from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class AntiSpamService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: dict[tuple[int, str], deque[float]] = defaultdict(deque)

    def hit(self, user_id: int, bucket: str, *, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()
        key = (user_id, bucket)
        with self._lock:
            queue = self._events[key]
            while queue and now - queue[0] > window_seconds:
                queue.popleft()
            if len(queue) >= limit:
                return False
            queue.append(now)
            return True
