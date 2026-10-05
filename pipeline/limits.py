"""One rate limiter shared by every worker: requests per second and tokens per second.

Requests are paced evenly, never in bursts. After a 429 the rate halves, at most once in
any 10 seconds, and then climbs back toward its ceiling.
"""

import threading
import time

HALVE_AT_MOST_EVERY = 10.0  # seconds


def estimate_tokens(body_bytes):
    """Tokens in a request body, estimated as bytes over 2.4 and rounded up (spec item 27)."""
    return max(1, -(-body_bytes * 10 // 24))


class Limiter:
    def __init__(
        self, requests_per_second=75, tokens_per_second=100_000, *, recover_per_second=1.0,
        clock=time.monotonic, sleep=time.sleep,
    ):  # fmt: skip
        self.ceiling = float(requests_per_second)
        self.tokens_per_second = float(tokens_per_second)
        self.recover_per_second = float(recover_per_second)
        self._clock, self._sleep = clock, sleep
        self._lock = threading.Lock()
        self._next_request = self._next_tokens = float("-inf")
        self._halved_rate = self._halved_at = None

    def rate(self):
        """Requests per second allowed right now."""
        if self._halved_at is None:
            return self.ceiling
        return min(self.ceiling, self._halved_rate + self.recover_per_second * (self._clock() - self._halved_at))

    def on_429(self):
        """The provider said slow down. Halve the rate unless it was halved in the last 10 seconds."""
        with self._lock:
            now = self._clock()
            if self._halved_at is None or now - self._halved_at >= HALVE_AT_MOST_EVERY:
                self._halved_rate, self._halved_at = max(1.0, self.rate() / 2), now

    def acquire(self, body_bytes):
        """Wait until one more request of this size fits under both limits."""
        with self._lock:
            now = self._clock()
            slot = max(now, self._next_request, self._next_tokens)
            self._next_request = slot + 1 / self.rate()
            self._next_tokens = slot + estimate_tokens(body_bytes) / self.tokens_per_second
        if slot > now:
            self._sleep(slot - now)
