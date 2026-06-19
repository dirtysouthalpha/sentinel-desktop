"""Tests for core.resilience — retry decorator and circuit breakers."""

from __future__ import annotations

import pytest

from core.resilience import (
    CircuitBreaker,
    CircuitBreakerOpen,
    RetryExhausted,
    circuit_breaker,
    get_all_breaker_stats,
    reset_all_breakers,
    retryable,
)

# ── Retry decorator tests ─────────────────────────────────────────────────────


class TestRetryable:
    def test_succeeds_on_first_try(self):
        calls = []

        @retryable(max_attempts=3)
        def fn():
            calls.append(1)
            return "ok"

        assert fn() == "ok"
        assert len(calls) == 1

    def test_retries_on_transient_error(self):
        calls = []

        @retryable(max_attempts=3, base_delay=0.001, exceptions=(OSError,))
        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise OSError("transient")
            return "success"

        result = fn()
        assert result == "success"
        assert len(calls) == 3

    def test_exhausts_all_attempts_and_raises(self):
        @retryable(max_attempts=3, base_delay=0.001, exceptions=(OSError,))
        def fn():
            raise OSError("always fails")

        with pytest.raises(RetryExhausted) as exc_info:
            fn()
        assert exc_info.value.attempts == 3
        assert isinstance(exc_info.value.last_exc, OSError)

    def test_non_transient_exception_propagates_immediately(self):
        calls = []

        @retryable(max_attempts=3, base_delay=0.001, exceptions=(OSError,))
        def fn():
            calls.append(1)
            raise ValueError("not retried")

        with pytest.raises(ValueError):
            fn()
        assert len(calls) == 1  # no retries

    def test_on_retry_callback_called(self):
        retries = []

        @retryable(
            max_attempts=3,
            base_delay=0.001,
            exceptions=(OSError,),
            on_retry=lambda n, e: retries.append(n),
        )
        def fn():
            raise OSError("fail")

        with pytest.raises(RetryExhausted):
            fn()
        assert retries == [1, 2]  # called after attempt 1 and 2

    def test_wraps_preserves_function_name(self):
        @retryable()
        def my_function():
            return True

        assert my_function.__name__ == "my_function"

    def test_single_attempt_fails_immediately(self):
        @retryable(max_attempts=1, base_delay=0.001, exceptions=(OSError,))
        def fn():
            raise OSError("fail")

        with pytest.raises(RetryExhausted) as exc_info:
            fn()
        assert exc_info.value.attempts == 1


# ── Circuit breaker tests ─────────────────────────────────────────────────────


class TestCircuitBreaker:
    def setup_method(self):
        # Use fresh breakers for each test
        self.cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=0.1)

    def test_starts_closed(self):
        assert self.cb.state == CircuitBreaker.CLOSED

    def test_closed_allows_calls(self):
        assert self.cb.allow_call() is True

    def test_trips_after_threshold_failures(self):
        for _ in range(3):
            self.cb.record_failure()
        assert self.cb.state == CircuitBreaker.OPEN

    def test_open_rejects_calls(self):
        for _ in range(3):
            self.cb.record_failure()
        assert self.cb.allow_call() is False

    def test_open_transitions_to_half_open_after_timeout(self):
        import time

        for _ in range(3):
            self.cb.record_failure()
        time.sleep(0.15)  # recovery_timeout=0.1
        assert self.cb.allow_call() is True
        assert self.cb.state == CircuitBreaker.HALF_OPEN

    def test_half_open_success_closes_breaker(self):
        import time

        cb = CircuitBreaker("t2", failure_threshold=2, recovery_timeout=0.05, success_threshold=2)
        for _ in range(2):
            cb.record_failure()
        time.sleep(0.1)
        cb.allow_call()  # → half_open
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_half_open_failure_reopens(self):
        import time

        for _ in range(3):
            self.cb.record_failure()
        time.sleep(0.15)
        self.cb.allow_call()
        self.cb.record_failure()
        assert self.cb.state == CircuitBreaker.OPEN

    def test_context_manager_records_success(self):
        with self.cb:
            pass
        assert self.cb._consecutive_failures == 0

    def test_context_manager_records_failure(self):
        with pytest.raises(ValueError):
            with self.cb:
                raise ValueError("oops")
        assert self.cb._consecutive_failures == 1

    def test_context_manager_raises_when_open(self):
        for _ in range(3):
            self.cb.record_failure()
        with pytest.raises(CircuitBreakerOpen):
            with self.cb:
                pass

    def test_reset_clears_state(self):
        for _ in range(3):
            self.cb.record_failure()
        self.cb.reset()
        assert self.cb.state == CircuitBreaker.CLOSED
        assert self.cb._consecutive_failures == 0

    def test_get_stats(self):
        self.cb.record_failure()
        stats = self.cb.get_stats()
        assert stats["name"] == "test"
        assert stats["state"] == "closed"
        assert stats["consecutive_failures"] == 1

    def test_success_resets_consecutive_failures(self):
        self.cb.record_failure()
        self.cb.record_failure()
        self.cb.record_success()
        assert self.cb._consecutive_failures == 0

    def test_two_consecutive_failures_dont_trip_with_threshold_3(self):
        self.cb.record_failure()
        self.cb.record_failure()
        assert self.cb.state == CircuitBreaker.CLOSED


# ── Registry tests ────────────────────────────────────────────────────────────


def test_circuit_breaker_registry_returns_same_instance():
    cb1 = circuit_breaker("ssh")
    cb2 = circuit_breaker("ssh")
    assert cb1 is cb2


def test_get_all_breaker_stats_returns_list():
    stats = get_all_breaker_stats()
    assert isinstance(stats, list)
    assert all("name" in s for s in stats)


def test_reset_all_breakers():
    cb = circuit_breaker("llm")
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN
    reset_all_breakers()
    assert cb.state == CircuitBreaker.CLOSED
