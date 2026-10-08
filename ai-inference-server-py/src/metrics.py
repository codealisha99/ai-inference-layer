"""Minimal in-process metrics rendered in the Prometheus text exposition format."""

from __future__ import annotations

import threading
from collections import defaultdict

_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._inferences: dict[str, int] = defaultdict(int)
        self._bucket_counts = [0] * len(_BUCKETS)
        self._duration_sum = 0.0
        self._duration_count = 0

    def observe_request(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self._requests[(method, route, status)] += 1
            self._duration_sum += seconds
            self._duration_count += 1
            for i, bound in enumerate(_BUCKETS):
                if seconds <= bound:
                    self._bucket_counts[i] += 1

    def observe_inferences(self, model_type: str, count: int = 1) -> None:
        with self._lock:
            self._inferences[model_type] += count

    def render(self, *, models: int, stored_inferences: int, uptime_seconds: float) -> str:
        with self._lock:
            lines = [
                "# HELP http_requests_total Total HTTP requests.",
                "# TYPE http_requests_total counter",
            ]
            for (method, route, status), n in sorted(self._requests.items()):
                lines.append(
                    f'http_requests_total{{method="{method}",route="{_esc(route)}",'
                    f'status="{status}"}} {n}'
                )
            lines += [
                "# HELP http_request_duration_seconds HTTP request latency.",
                "# TYPE http_request_duration_seconds histogram",
            ]
            for bound, n in zip(_BUCKETS, self._bucket_counts, strict=True):
                lines.append(f'http_request_duration_seconds_bucket{{le="{bound}"}} {n}')
            lines += [
                f'http_request_duration_seconds_bucket{{le="+Inf"}} {self._duration_count}',
                f"http_request_duration_seconds_sum {self._duration_sum:.6f}",
                f"http_request_duration_seconds_count {self._duration_count}",
                "# HELP inferences_total Inferences executed, by model type.",
                "# TYPE inferences_total counter",
            ]
            for typ, n in sorted(self._inferences.items()):
                lines.append(f'inferences_total{{model_type="{_esc(typ)}"}} {n}')
            lines += [
                "# HELP models Registered models.",
                "# TYPE models gauge",
                f"models {models}",
                "# HELP stored_inferences Inferences currently retained in memory.",
                "# TYPE stored_inferences gauge",
                f"stored_inferences {stored_inferences}",
                "# HELP uptime_seconds Seconds since the server started.",
                "# TYPE uptime_seconds gauge",
                f"uptime_seconds {uptime_seconds:.3f}",
            ]
        return "\n".join(lines) + "\n"
