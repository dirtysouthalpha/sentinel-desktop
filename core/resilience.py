"""Sentinel Desktop v14.0 — Resilience Engine.

Retry decorator with exponential backoff + jitter, and circuit breakers
per subsystem (SSH, browser, OCR, LLM, desktop).

Usage::

    from core.resilience import retryable, circuit_breaker, CircuitBreakerOpen

    @retryable(max_attempts=3, exceptions=(OSError, TimeoutError))
    def flaky_click(x, y):
        ...

    # Manual circuit breaker usage
    cb = circuit_breaker("ocr")
    with cb:
        result = ocr.read_screen()
"""

from __future__ import annotations

import functools
import logging
import random
import time
from collections import deque
from collections.abc import Callable
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

# Retry defaults
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_MAX_DELAY = 30.0  # seconds
DEFAULT_JITTER = 0.3  # fraction of delay added as jitter

# Circuit breaker defaults
DEFAULT_FAILURE_THRESHOLD = 3  # consecutive failures before open
DEFAULT_RECOVERY_TIMEOUT = 60.0  # seconds in open state before half-open
DEFAULT_SUCCESS_THRESHOLD = 2  # successes in half-open before closed

# Transient error types that warrant retry
TRANSIENT_EXCEPTIONS = (
    TimeoutError,
    ConnectionError,
    ConnectionResetError,
    ConnectionAbortedError,
    ConnectionRefusedError,
    OSError,
)


# ── Retry decorator ──────────────────────────────────────────────────────────


class RetryExhausted(Exception):
    """Raised when all retry attempts have been consumed."""

    def __init__(self, attempts: int, last_exc: Exception) -> None:
        """Initialize with attempt count and the last caught exception."""
        super().__init__(f"All {attempts} retry attempts failed: {last_exc}")
        self.attempts = attempts
        self.last_exc = last_exc


def retryable(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter: float = DEFAULT_JITTER,
    exceptions: tuple[type[Exception], ...] = TRANSIENT_EXCEPTIONS,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Callable:
    """Decorator: retry the wrapped function with exponential back-off.

    Only retries on *exceptions* — non-transient errors propagate immediately.

    Args:
        max_attempts: Total attempts (including the first try). Default 3.
        base_delay:   Initial wait in seconds. Default 1.0.
        max_delay:    Cap on wait time. Default 30.0.
        jitter:       Random fraction of delay to add (prevents thundering herd).
        exceptions:   Exception types that trigger a retry. Default: transient I/O.
        on_retry:     Optional callback(attempt_number, exception) called on each retry.

    Raises:
        RetryExhausted: When all attempts fail.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        break
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    delay += delay * random.uniform(0, jitter)  # noqa: S311
                    logger.info(
                        "Retry %d/%d for %s after %.1fs (reason: %s)",
                        attempt,
                        max_attempts,
                        fn.__name__,
                        delay,
                        exc,
                    )
                    if on_retry:
                        on_retry(attempt, exc)
                    time.sleep(delay)
                except Exception:
                    # Non-transient: let it propagate immediately
                    raise
            raise RetryExhausted(max_attempts, last_exc)  # type: ignore[arg-type]

        return wrapper

    return decorator


# ── Circuit Breaker ──────────────────────────────────────────────────────────


class CircuitBreakerOpen(Exception):
    """Raised when a circuit is open and calls are rejected."""

    def __init__(self, subsystem: str) -> None:
        """Initialize with the name of the tripped subsystem."""
        super().__init__(f"Circuit breaker open for '{subsystem}' — call rejected")
        self.subsystem = subsystem


class CircuitBreaker:
    """Per-subsystem circuit breaker with closed / open / half-open states.

    States::
        CLOSED     — normal operation
        OPEN       — failures exceeded threshold, calls rejected immediately
        HALF_OPEN  — cooling down, a probe call is allowed
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        name: str,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        recovery_timeout: float = DEFAULT_RECOVERY_TIMEOUT,
        success_threshold: int = DEFAULT_SUCCESS_THRESHOLD,
    ) -> None:
        """Initialize circuit breaker.

        Args:
            name:              Subsystem name for logging.
            failure_threshold: Consecutive failures to trip. Default 3.
            recovery_timeout:  Seconds in OPEN before transitioning to HALF_OPEN.
            success_threshold: Successes in HALF_OPEN to return to CLOSED.
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = self.CLOSED
        self._failures: deque[float] = deque()  # timestamps of failures
        self._consecutive_failures = 0
        self._half_open_successes = 0
        self._opened_at: float | None = None
        self._lock = Lock()

    @property
    def state(self) -> str:
        """Current state string: 'closed', 'open', or 'half_open'."""
        return self._state

    def _transition(self, new_state: str) -> None:
        """Transition to *new_state* and log."""
        if self._state != new_state:
            logger.warning("CircuitBreaker '%s': %s → %s", self.name, self._state, new_state)
            self._state = new_state

    def record_success(self) -> None:
        """Record a successful call — may close a half-open circuit."""
        with self._lock:
            self._consecutive_failures = 0
            if self._state == self.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.success_threshold:
                    self._half_open_successes = 0
                    self._opened_at = None
                    self._transition(self.CLOSED)

    def record_failure(self) -> None:
        """Record a failed call — may open a closed circuit."""
        with self._lock:
            self._consecutive_failures += 1
            self._failures.append(time.monotonic())
            if self._state == self.HALF_OPEN:
                # Probe failed — back to open
                self._half_open_successes = 0
                self._opened_at = time.monotonic()
                self._transition(self.OPEN)
            elif self._state == self.CLOSED:
                if self._consecutive_failures >= self.failure_threshold:
                    self._opened_at = time.monotonic()
                    self._transition(self.OPEN)

    def allow_call(self) -> bool:
        """Return True if the call should proceed."""
        with self._lock:
            if self._state == self.CLOSED:
                return True
            if self._state == self.OPEN:
                elapsed = time.monotonic() - (self._opened_at or 0)
                if elapsed >= self.recovery_timeout:
                    self._half_open_successes = 0
                    self._transition(self.HALF_OPEN)
                    return True
                return False
            # HALF_OPEN: allow one probe
            return True

    def __enter__(self) -> CircuitBreaker:
        """Context-manager entry: raise CircuitBreakerOpen if tripped."""
        if not self.allow_call():
            raise CircuitBreakerOpen(self.name)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        """Record success/failure based on whether an exception was raised."""
        if exc_type is None:
            self.record_success()
        else:
            self.record_failure()
        return False  # never suppress exceptions

    def get_stats(self) -> dict[str, Any]:
        """Return current breaker state and counters."""
        return {
            "name": self.name,
            "state": self._state,
            "consecutive_failures": self._consecutive_failures,
            "total_failures": len(self._failures),
        }

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED."""
        with self._lock:
            self._state = self.CLOSED
            self._consecutive_failures = 0
            self._half_open_successes = 0
            self._failures.clear()
            self._opened_at = None
        logger.info("CircuitBreaker '%s': manually reset to CLOSED", self.name)


# ── Breaker registry ─────────────────────────────────────────────────────────

_BREAKERS: dict[str, CircuitBreaker] = {}
_BREAKER_LOCK = Lock()

# Pre-defined subsystem breakers
SUBSYSTEMS = ("ssh", "browser", "ocr", "llm", "desktop", "netops")


def circuit_breaker(name: str) -> CircuitBreaker:
    """Return the CircuitBreaker for *name*, creating it if needed."""
    with _BREAKER_LOCK:
        if name not in _BREAKERS:
            _BREAKERS[name] = CircuitBreaker(name)
        return _BREAKERS[name]


def get_all_breaker_stats() -> list[dict[str, Any]]:
    """Return stats for all registered circuit breakers."""
    with _BREAKER_LOCK:
        return [cb.get_stats() for cb in _BREAKERS.values()]


def reset_all_breakers() -> None:
    """Reset all circuit breakers (for testing / operator intervention)."""
    with _BREAKER_LOCK:
        for cb in _BREAKERS.values():
            cb.reset()


# Pre-initialise standard subsystem breakers
for _sub in SUBSYSTEMS:
    circuit_breaker(_sub)
