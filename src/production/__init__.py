"""
Production infrastructure & hardening modules for MedGemma.

Includes:
- Rate limiting (slowapi)
- Circuit breakers (resilience pattern)
- Prometheus monitoring & metrics
- Health checks & status endpoints
- Request timeouts
"""

from src.production.rate_limiter import RateLimitConfig, get_limiter, RateLimitMiddleware
from src.production.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    get_circuit_breaker_registry,
    init_circuit_breakers,
    with_timeout,
    TimeoutError,
)
from src.production.metrics import MetricsCollector, RequestMetricsMiddleware, PROMETHEUS_AVAILABLE

__all__ = [
    "RateLimitConfig",
    "get_limiter",
    "RateLimitMiddleware",
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "get_circuit_breaker_registry",
    "init_circuit_breakers",
    "with_timeout",
    "TimeoutError",
    "MetricsCollector",
    "RequestMetricsMiddleware",
    "PROMETHEUS_AVAILABLE",
]
