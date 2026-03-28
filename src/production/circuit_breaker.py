"""
Request timeouts and circuit breaker pattern for resilience.
Prevents cascading failures and resource exhaustion.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker implementation for external service calls."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception,
    ):
        """Initialize circuit breaker.

        Args:
            name: Circuit breaker identifier
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception type to catch
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info(f"Circuit breaker '{self.name}' entering HALF_OPEN state")
            else:
                raise RuntimeError(f"Circuit breaker '{self.name}' is OPEN")

        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        """Handle successful call."""
        self.failure_count = 0

        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= 2:
                self.state = CircuitBreakerState.CLOSED
                self.success_count = 0
                logger.info(f"Circuit breaker '{self.name}' is now CLOSED")

    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(
                f"Circuit breaker '{self.name}' opened after {self.failure_count} failures"
            )

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self.last_failure_time is None:
            return True
        return time.time() - self.last_failure_time >= self.recovery_timeout

    def get_state(self) -> str:
        """Get current circuit breaker state."""
        return self.state.value


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""

    def __init__(self):
        self.breakers: dict[str, CircuitBreaker] = {}

    def register(self, name: str, breaker: CircuitBreaker) -> None:
        """Register a circuit breaker."""
        self.breakers[name] = breaker
        logger.info(f"Circuit breaker '{name}' registered")

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name."""
        return self.breakers.get(name)

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
    ) -> CircuitBreaker:
        """Get existing or create new circuit breaker."""
        if name not in self.breakers:
            breaker = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
            self.register(name, breaker)
        return self.breakers[name]

    def get_status(self) -> dict[str, str]:
        """Get status of all circuit breakers."""
        return {name: breaker.get_state() for name, breaker in self.breakers.items()}


# Global circuit breaker registry
_circuit_breaker_registry = CircuitBreakerRegistry()


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get global circuit breaker registry."""
    return _circuit_breaker_registry


# ── Timeout utilities ────────────────────────────────────────────────────


class TimeoutError(Exception):
    """Custom timeout exception."""
    pass


async def with_timeout(
    coro, timeout_seconds: float, operation_name: str = "operation"
) -> Any:
    """Execute coroutine with timeout.

    Args:
        coro: Coroutine to execute
        timeout_seconds: Timeout in seconds
        operation_name: Name for logging

    Returns:
        Coroutine result

    Raises:
        TimeoutError: If timeout exceeded
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.error(f"{operation_name} exceeded timeout of {timeout_seconds}s")
        raise TimeoutError(
            f"{operation_name} exceeded timeout of {timeout_seconds}s"
        ) from None


# Default timeout configurations
TIMEOUT_CONFIG = {
    "firestore_read": 5.0,
    "firestore_write": 10.0,
    "llm_inference": 60.0,
    "pubmed_search": 30.0,
    "image_analysis": 45.0,
    "asr_transcription": 120.0,
    "http_request": 30.0,
}


def get_timeout(operation: str) -> float:
    """Get timeout for operation."""
    return TIMEOUT_CONFIG.get(operation, 30.0)


# ── Service-specific circuit breakers ────────────────────────────────────


def init_circuit_breakers():
    """Initialize service circuit breakers."""
    registry = get_circuit_breaker_registry()

    # Firestore circuit breaker (strict: 3 failures = open)
    registry.get_or_create("firestore", failure_threshold=3, recovery_timeout=30)

    # LLM inference circuit breaker (lenient: 10 failures = open)
    registry.get_or_create("llm_inference", failure_threshold=10, recovery_timeout=60)

    # PubMed circuit breaker (medium: 5 failures = open)
    registry.get_or_create("pubmed", failure_threshold=5, recovery_timeout=45)

    # Image analysis circuit breaker (lenient: 8 failures = open)
    registry.get_or_create("image_analysis", failure_threshold=8, recovery_timeout=60)

    # ASR circuit breaker (medium: 5 failures = open)
    registry.get_or_create("asr", failure_threshold=5, recovery_timeout=60)

    logger.info("Circuit breakers initialized")
