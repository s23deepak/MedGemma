"""
Prometheus metrics and monitoring for production observability.
Tracks request latency, throughput, errors, and system health.
"""

import logging
import time
import multiprocessing
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Import prometheus-client
try:
    from prometheus_client import Counter, Histogram, Gauge, start_http_server, REGISTRY
    from prometheus_client.registry import REGISTRY
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus-client not installed. Install with: uv add prometheus-client")


# ── Metrics Definitions ────────────────────────────────────────────────────

if PROMETHEUS_AVAILABLE:
    # Request metrics
    REQUEST_COUNT = Counter(
        "medgemma_requests_total",
        "Total number of requests",
        ["method", "endpoint", "status"],
    )

    REQUEST_LATENCY = Histogram(
        "medgemma_request_duration_seconds",
        "Request duration in seconds",
        ["method", "endpoint"],
        buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )

    # Error metrics
    ERROR_COUNT = Counter(
        "medgemma_errors_total",
        "Total number of errors",
        ["error_type", "endpoint"],
    )

    # Rate limit metrics
    RATE_LIMIT_EXCEEDED = Counter(
        "medgemma_rate_limits_exceeded_total",
        "Total rate limit exceeded",
        ["endpoint", "user_role"],
    )

    # Firestore operation metrics
    FIRESTORE_OPERATION_DURATION = Histogram(
        "medgemma_firestore_duration_seconds",
        "Firestore operation duration",
        ["operation", "collection"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0),
    )

    FIRESTORE_OPERATIONS_TOTAL = Counter(
        "medgemma_firestore_operations_total",
        "Total Firestore operations",
        ["operation", "collection", "status"],
    )

    # Model inference metrics
    INFERENCE_DURATION = Histogram(
        "medgemma_inference_duration_seconds",
        "Model inference duration",
        ["model", "task"],
        buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0),
    )

    INFERENCE_TOTAL = Counter(
        "medgemma_inferences_total",
        "Total model inferences",
        ["model", "task", "status"],
    )

    # System health metrics
    ACTIVE_SESSIONS = Gauge(
        "medgemma_active_sessions",
        "Number of active sessions",
    )

    QUEUE_SIZE = Gauge(
        "medgemma_queue_size",
        "Request queue size",
    )

    MODEL_LOAD_TIME = Histogram(
        "medgemma_model_load_seconds",
        "Model load time",
        ["model"],
    )

    # Cache metrics
    CACHE_HITS = Counter(
        "medgemma_cache_hits_total",
        "Cache hits",
        ["cache_name"],
    )

    CACHE_MISSES = Counter(
        "medgemma_cache_misses_total",
        "Cache misses",
        ["cache_name"],
    )

    # HIPAA compliance metrics
    HIPAA_ACCESS_DENIED = Counter(
        "medgemma_hipaa_access_denied_total",
        "HIPAA access denied count",
        ["user_role", "reason"],
    )

    HIPAA_AUDIT_LOGS = Counter(
        "medgemma_hipaa_audit_logs_total",
        "HIPAA audit log entries",
        ["event_type", "severity"],
    )

else:
    # Dummy implementations when prometheus not available
    REQUEST_COUNT = type("DummyCounter", (), {"labels": lambda *a, **k: type("X", (), {"inc": lambda *a, **k: None})()})()
    REQUEST_LATENCY = type("DummyHistogram", (), {"labels": lambda *a, **k: type("X", (), {"observe": lambda x: None})()})()
    ERROR_COUNT = REQUEST_COUNT
    RATE_LIMIT_EXCEEDED = REQUEST_COUNT
    FIRESTORE_OPERATION_DURATION = REQUEST_LATENCY
    FIRESTORE_OPERATIONS_TOTAL = REQUEST_COUNT
    INFERENCE_DURATION = REQUEST_LATENCY
    INFERENCE_TOTAL = REQUEST_COUNT
    ACTIVE_SESSIONS = type("DummyGauge", (), {"set": lambda x: None})()
    QUEUE_SIZE = ACTIVE_SESSIONS
    MODEL_LOAD_TIME = REQUEST_LATENCY
    CACHE_HITS = REQUEST_COUNT
    CACHE_MISSES = REQUEST_COUNT
    HIPAA_ACCESS_DENIED = REQUEST_COUNT
    HIPAA_AUDIT_LOGS = REQUEST_COUNT


# ── Monitoring Utilities ────────────────────────────────────────────────────


class MetricsCollector:
    """Utility class for recording metrics."""

    @staticmethod
    def start_prometheus_server(port: int = 8001):
        """Start Prometheus metrics server."""
        if not PROMETHEUS_AVAILABLE:
            logger.warning("Prometheus not available - metrics server not started")
            return

        # In multi-worker uvicorn deployments, each worker imports the module.
        # Only allow the top-level process to bind the sidecar metrics port.
        if multiprocessing.current_process().name != "MainProcess":
            logger.info("Skipping Prometheus metrics sidecar in worker process")
            return

        if os.environ.get("DISABLE_PROMETHEUS_SIDECAR", "false").lower() in ("1", "true", "yes"):
            logger.info("Prometheus metrics sidecar disabled via DISABLE_PROMETHEUS_SIDECAR")
            return

        try:
            start_http_server(port)
            logger.info(f"Prometheus metrics server started on port {port}")
        except Exception as e:
            logger.error(f"Failed to start Prometheus metrics server: {e}")

    @staticmethod
    def record_request(method: str, endpoint: str, status: int, duration: float):
        """Record HTTP request metrics."""
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)

    @staticmethod
    def record_error(error_type: str, endpoint: str):
        """Record error metric."""
        ERROR_COUNT.labels(error_type=error_type, endpoint=endpoint).inc()

    @staticmethod
    def record_rate_limit(endpoint: str, user_role: str = "unknown"):
        """Record rate limit exceeded."""
        RATE_LIMIT_EXCEEDED.labels(endpoint=endpoint, user_role=user_role).inc()

    @staticmethod
    def record_firestore_operation(operation: str, collection: str, duration: float, status: str = "success"):
        """Record Firestore operation metrics."""
        FIRESTORE_OPERATION_DURATION.labels(operation=operation, collection=collection).observe(duration)
        FIRESTORE_OPERATIONS_TOTAL.labels(operation=operation, collection=collection, status=status).inc()

    @staticmethod
    def record_inference(model: str, task: str, duration: float, status: str = "success"):
        """Record model inference metrics."""
        INFERENCE_DURATION.labels(model=model, task=task).observe(duration)
        INFERENCE_TOTAL.labels(model=model, task=task, status=status).inc()

    @staticmethod
    def set_active_sessions(count: int):
        """Set active session count."""
        ACTIVE_SESSIONS.set(count)

    @staticmethod
    def set_queue_size(size: int):
        """Set request queue size."""
        QUEUE_SIZE.set(size)

    @staticmethod
    def record_cache_hit(cache_name: str):
        """Record cache hit."""
        CACHE_HITS.labels(cache_name=cache_name).inc()

    @staticmethod
    def record_cache_miss(cache_name: str):
        """Record cache miss."""
        CACHE_MISSES.labels(cache_name=cache_name).inc()

    @staticmethod
    def record_hipaa_access_denied(user_role: str, reason: str):
        """Record HIPAA access denied."""
        HIPAA_ACCESS_DENIED.labels(user_role=user_role, reason=reason).inc()

    @staticmethod
    def record_hipaa_audit_log(event_type: str, severity: str = "INFO"):
        """Record HIPAA audit log."""
        HIPAA_AUDIT_LOGS.labels(event_type=event_type, severity=severity).inc()


class RequestMetricsMiddleware:
    """ASGI middleware to collect request metrics."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        method = scope["method"]
        path = scope["path"]

        async def send_with_metrics(message):
            if message["type"] == "http.response.start":
                status = message["status"]
                duration = time.time() - start_time

                MetricsCollector.record_request(
                    method=method,
                    endpoint=path,
                    status=status,
                    duration=duration,
                )

            await send(message)

        await self.app(scope, receive, send_with_metrics)
