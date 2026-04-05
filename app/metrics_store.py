"""
Module-level Prometheus metrics storage.

All mutations are protected by a threading.Lock so they are safe within a
single gunicorn worker (threaded mode). Counters are per-process — each worker
maintains its own copy, which is standard for push-style scraping setups.
"""

import threading
from collections import defaultdict

_lock = threading.Lock()

# http_requests_total{method, path, status} -> int
REQUEST_COUNTS: dict[tuple[str, str, str], int] = defaultdict(int)

# http_request_duration_seconds histogram
_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
# bucket upper-bound -> cumulative count
DURATION_BUCKETS: dict[float, int] = {b: 0 for b in _BUCKETS}
DURATION_SUM: list[float] = [0.0]   # wrapped in list so lock-free reads stay consistent
DURATION_COUNT: list[int] = [0]

# Cache counters
CACHE_HITS: list[int] = [0]
CACHE_MISSES: list[int] = [0]


def record_request(method: str, path: str, status: int, duration_seconds: float) -> None:
    with _lock:
        REQUEST_COUNTS[(method, path, str(status))] += 1
        for bound in _BUCKETS:
            if duration_seconds <= bound:
                DURATION_BUCKETS[bound] += 1
        DURATION_SUM[0] += duration_seconds
        DURATION_COUNT[0] += 1


def increment_cache_hit() -> None:
    with _lock:
        CACHE_HITS[0] += 1


def increment_cache_miss() -> None:
    with _lock:
        CACHE_MISSES[0] += 1


def buckets_snapshot() -> list[tuple[float, int]]:
    """Return list of (le, cumulative_count) pairs in ascending order."""
    with _lock:
        # cumulative: each bucket includes all observations <= le
        cumulative = 0
        result = []
        for bound in _BUCKETS:
            cumulative += DURATION_BUCKETS[bound]
            result.append((bound, cumulative))
        result.append((float("inf"), DURATION_COUNT[0]))
        return result
