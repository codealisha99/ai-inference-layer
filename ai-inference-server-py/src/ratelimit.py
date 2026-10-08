"""Token-bucket rate limiting with bounded memory."""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    limit: int  # bucket capacity (burst)
    remaining: int  # whole tokens left after this request
    retry_after: int  # seconds until a token is available (0 when allowed)
    reset: int  # seconds until the bucket is full again


class RateLimiter:
    """One bucket per client: ``burst`` tokens, refilled at ``per_minute / 60`` per second.

    A request costs one token. The bucket table is bounded by ``max_clients``: idle buckets
    (already full again) are dropped first, then the least recently used, so a flood of
    distinct clients cannot grow memory without limit.
    """

    def __init__(
        self,
        per_minute: int,
        burst: int | None = None,
        *,
        max_clients: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if per_minute < 1:
            raise ValueError("per_minute must be >= 1")
        self.rate = per_minute / 60.0
        self.burst = burst if burst is not None else per_minute
        if self.burst < 1:
            raise ValueError("burst must be >= 1")
        self._max_clients = max_clients
        self._clock = clock
        self._lock = threading.Lock()
        # client -> (tokens, last_refill_time); most recently used last
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()

    def check(self, client: str) -> Decision:
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.pop(client, (float(self.burst), now))
            tokens = min(float(self.burst), tokens + (now - last) * self.rate)
            allowed = tokens >= 1.0
            if allowed:
                tokens -= 1.0
            self._buckets[client] = (tokens, now)
            if len(self._buckets) > self._max_clients:
                self._evict(now)
            retry_after = 0 if allowed else math.ceil((1.0 - tokens) / self.rate)
            reset = math.ceil((self.burst - tokens) / self.rate)
            return Decision(allowed, self.burst, int(tokens), retry_after, reset)

    def _evict(self, now: float) -> None:
        full_after = self.burst / self.rate
        for key in [k for k, (_, last) in self._buckets.items() if now - last >= full_after]:
            if len(self._buckets) <= self._max_clients:
                return
            del self._buckets[key]
        while len(self._buckets) > self._max_clients:
            self._buckets.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._buckets)
