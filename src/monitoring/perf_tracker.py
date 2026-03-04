"""
Performance Tracker — lightweight latency profiler for clinical API operations.

Usage:
    from src.monitoring.perf_tracker import track_perf, get_stats

    @track_perf("council_deliberation")
    async def my_route_handler(...):
        ...

    # Expose via GET /api/metrics
    stats = get_stats()
    # {"council_deliberation": {"avg_ms": 312.4, "min_ms": 201.1, "max_ms": 489.2, "count": 7}}
"""

from __future__ import annotations

import asyncio
import functools
import time
from collections import deque
from typing import Any, Callable

# ── Module-level timing store ─────────────────────────────────────────────────

_timings: dict[str, deque[float]] = {}
_MAX_SAMPLES = 200


def _record(operation_name: str, elapsed_ms: float) -> None:
    """Append a timing sample (thread-safe for CPython GIL-protected deque ops)."""
    if operation_name not in _timings:
        _timings[operation_name] = deque(maxlen=_MAX_SAMPLES)
    _timings[operation_name].append(elapsed_ms)


# ── Decorator ─────────────────────────────────────────────────────────────────

def track_perf(operation_name: str) -> Callable:
    """
    Decorator factory that records wall-clock latency in milliseconds.

    Works on both sync and async functions. Uses functools.wraps to preserve
    the original function's __name__ and __doc__ so FastAPI route registration
    and OpenAPI schema generation work correctly.

    Args:
        operation_name: Key used in get_stats() output.
    """
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                t0 = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    _record(operation_name, (time.perf_counter() - t0) * 1000)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                t0 = time.perf_counter()
                try:
                    return func(*args, **kwargs)
                finally:
                    _record(operation_name, (time.perf_counter() - t0) * 1000)
            return sync_wrapper
    return decorator


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_stats() -> dict[str, dict]:
    """
    Return aggregated performance statistics for all tracked operations.

    Returns a dict keyed by operation name:
        {
            "council_deliberation": {
                "avg_ms": 312.4,
                "min_ms": 201.1,
                "max_ms": 489.2,
                "count": 7,
            },
            ...
        }

    Operations with no recorded samples are excluded.
    """
    result: dict[str, dict] = {}
    for name, samples in _timings.items():
        data = list(samples)
        if not data:
            continue
        result[name] = {
            "avg_ms": round(sum(data) / len(data), 2),
            "min_ms": round(min(data), 2),
            "max_ms": round(max(data), 2),
            "count": len(data),
        }
    return result
