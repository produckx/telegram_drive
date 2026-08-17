"""
Simple in-memory rate limiter (sliding window) and login brute-force guard.

Keeps things in-process so it doesn't need Redis/external deps. Each key
(e.g. "register:1.2.3.4") gets a deque of timestamps; we evict old entries
beyond the window before counting.
"""
import time
from collections import deque, defaultdict
from threading import Lock
from typing import Deque, Dict, Tuple


class RateLimiter:
    def __init__(self):
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Return True if the request is allowed, False if it should be blocked."""
        now = time.monotonic()
        with self._lock:
            dq = self._hits[key]
            while dq and now - dq[0] > window_seconds:
                dq.popleft()
            if len(dq) >= max_requests:
                return False
            dq.append(now)
            return True

    def retry_after(self, key: str, window_seconds: int) -> int:
        """Return how many seconds until the next request would be allowed."""
        now = time.monotonic()
        with self._lock:
            dq = self._hits.get(key)
            if not dq:
                return 0
            return max(1, int(window_seconds - (now - dq[0])))


class LoginGuard:
    """Track failed login attempts per (ip, email). After `max_failures` within
    `window_seconds`, block the key for `block_seconds`."""

    def __init__(self, max_failures: int = 5, window_seconds: int = 300, block_seconds: int = 900):
        self._failures: Dict[str, Deque[float]] = defaultdict(deque)
        self._blocks: Dict[str, float] = {}
        self._lock = Lock()
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.block_seconds = block_seconds

    def is_blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            until = self._blocks.get(key)
            if until and until > now:
                return True
            if until and until <= now:
                del self._blocks[key]
                self._failures.pop(key, None)
            return False

    def retry_after(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            until = self._blocks.get(key)
            if until and until > now:
                return max(1, int(until - now))
            return 0

    def record_failure(self, key: str):
        now = time.monotonic()
        with self._lock:
            dq = self._failures[key]
            while dq and now - dq[0] > self.window_seconds:
                dq.popleft()
            dq.append(now)
            if len(dq) >= self.max_failures:
                self._blocks[key] = now + self.block_seconds

    def clear(self, key: str):
        with self._lock:
            self._failures.pop(key, None)
            self._blocks.pop(key, None)


rate_limiter = RateLimiter()
login_guard = LoginGuard()


def get_client_ip(request) -> str:
    """Get the public client IP. Honors X-Forwarded-For first (when behind a proxy)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip()
        if ip:
            return ip
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
