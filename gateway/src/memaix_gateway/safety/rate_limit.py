# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sliding-window rate limiter (in-memory, process-local).

Sufficient for single-tenant usage.  For multi-process deployments,
swap the deque store for a Redis backend with the same interface.

Defaults (SAFETY.md §3):
  user    — 60 calls / 60 s
  project — 120 calls / 60 s
"""

from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    """Thread-safe sliding-window rate limiter."""

    def __init__(self) -> None:
        self._windows: dict[str, deque] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_s: int) -> bool:
        """Return True if the call is within rate, False if the limit is exceeded.

        Calling this method always counts as one call attempt (timestamps are
        appended on the first successful check, not on denial).
        """
        now = time.monotonic()
        cutoff = now - window_s
        with self._lock:
            if key not in self._windows:
                self._windows[key] = deque()
            dq = self._windows[key]
            # Evict expired timestamps
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(now)
            return True

    def check_user(self, user_id: str) -> bool:
        """60 calls per 60 s per user."""
        return self.check(f"user:{user_id}", limit=60, window_s=60)

    def check_project(self, project: str) -> bool:
        """120 calls per 60 s per project."""
        return self.check(f"project:{project}", limit=120, window_s=60)

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def _inject_timestamps(self, key: str, timestamps: list[float]) -> None:
        """For testing: pre-populate a window with known timestamps."""
        with self._lock:
            self._windows[key] = deque(timestamps)

    def _get_timestamps(self, key: str) -> list[float]:
        """For testing: inspect the current window."""
        with self._lock:
            return list(self._windows.get(key, []))


# Module-level default instance used by server.py
rate_limiter = RateLimiter()
