"""Provider backoff uses fake errors/clock: no SDK request or real sleep."""

import json
import logging
from types import SimpleNamespace

import pytest

from core.config import AppConfig, BudgetConfig
from core.gateway import BudgetExceeded, LLMManager


class ProviderFailure(Exception):
    def __init__(self, status=429, *, headers=None, details=None, response_json=None):
        super().__init__("PRIVATE_PROVIDER_BODY credentials=PRIVATE_KEY")
        self.status_code = status
        self.response = SimpleNamespace(headers=headers or {})
        self.details = details
        self.response_json = response_json


class Clock:
    def __init__(self, monkeypatch):
        self.now = 100.0
        self.sleeps = []
        self.after_sleep = None
        monkeypatch.setattr("core.gateway.time.monotonic", lambda: self.now)
        monkeypatch.setattr("core.gateway.time.sleep", self.sleep)

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds
        if self.after_sleep:
            self.after_sleep()


def runner(monkeypatch, responses, *, provider="gemini", **budget):
    clock = Clock(monkeypatch)
    manager = LLMManager(config=AppConfig(budget=BudgetConfig(**budget)), credentials={})
    monkeypatch.setattr(manager, "_client", lambda *args: object())
    values = iter(responses)
    calls = []

    def call(actual_provider, *args):
        calls.append((actual_provider, clock.now))
        value = next(values)
        if isinstance(value, Exception):
            raise value
        return value, {}, "STOP"

    monkeypatch.setattr(manager, "_provider_call", call)
    return manager, clock, calls, lambda: manager.call_llm("q", preferred_provider=provider)


def retry_info(delay):
    return {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}


@pytest.mark.parametrize("header", ["Retry-After", "retry-after"])
@pytest.mark.parametrize("provider", ["gemini", "openai"])
def test_numeric_http_retry_after_delays_next_attempt(monkeypatch, header, provider):
    manager, clock, calls, run = runner(
        monkeypatch, [ProviderFailure(headers={header: "3.5"}), "ok"], provider=provider
    )
    assert run()[0] == "ok"
    assert calls == [(provider, 100.0), (provider, 103.5)]
    assert sum(clock.sleeps) == pytest.approx(3.5)
    assert max(clock.sleeps) <= 0.1
    assert manager._attempt_count == 2
    assert [record["status"] for record in manager.calls] == ["error", "success"]


@pytest.mark.parametrize("attribute", ["details", "response_json"])
@pytest.mark.parametrize("shape", ["body", "error", "list"])
def test_gemini_retry_info_honors_longest_numeric_hint(monkeypatch, attribute, shape):
    details = [retry_info("5.125s"), {"@type": "type.googleapis.com/google.rpc.ErrorInfo"}]
    payload = {"details": details} if shape == "body" else {"error": {"details": details}}
    if shape == "list":
        payload = details
    error = ProviderFailure(headers={"Retry-After": "3"}, **{attribute: payload})
    _, clock, calls, run = runner(monkeypatch, [error, "ok"])
    assert run()[0] == "ok"
    assert calls[1][1] - calls[0][1] == pytest.approx(5.125)
    assert sum(clock.sleeps) == pytest.approx(5.125)


def test_429_without_hint_has_bounded_exponential_backoff(monkeypatch):
    manager, clock, calls, run = runner(
        monkeypatch, [ProviderFailure(), ProviderFailure(), "ok"], transient_retries=2
    )
    assert run()[0] == "ok"
    assert [timestamp for _, timestamp in calls] == [100.0, 102.0, 106.0]
    assert sum(clock.sleeps) == pytest.approx(6.0)
    assert manager._attempt_count == 3


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_other_transient_status_retains_shorter_backoff(monkeypatch, status):
    _, clock, calls, run = runner(monkeypatch, [ProviderFailure(status), "ok"])
    assert run()[0] == "ok"
    assert calls[1][1] - calls[0][1] == pytest.approx(0.25)
    assert sum(clock.sleeps) == pytest.approx(0.25)


@pytest.mark.parametrize(
    "error",
    [
        ProviderFailure(headers={"Retry-After": "Wed, 21 Oct 2030 07:28:00 GMT"}),
        ProviderFailure(headers={"Retry-After": "2 PRIVATE_BODY"}),
        ProviderFailure(headers={"Retry-After": "NaN"}),
        ProviderFailure(headers={"Retry-After": "1e3"}),
        ProviderFailure(headers={"Retry-After": -1}),
        ProviderFailure(headers={"Retry-After": True}),
        ProviderFailure(headers={"Retry-After": float("inf")}),
        ProviderFailure(headers={"Retry-After": 1 << 10000}),
        ProviderFailure(details={"retryDelay": "40s"}),
        ProviderFailure(details={"details": [{"@type": "other.RetryInfo", "retryDelay": "40s"}]}),
        ProviderFailure(details={"details": [retry_info("-4s"), retry_info("NaNs")]}),
        ProviderFailure(details={"details": [retry_info("4.0000000001s")]}),
        ProviderFailure(details={"details": [retry_info(4)]}),
        ProviderFailure(details={"error": {"message": "Retry after 40s", "retryDelay": "40s"}}),
    ],
)
def test_unrelated_or_malformed_metadata_does_not_control_wait(monkeypatch, error):
    _, clock, _, run = runner(monkeypatch, [error, "ok"])
    assert run()[0] == "ok"
    assert sum(clock.sleeps) == pytest.approx(2.0)


def test_gemini_metadata_is_not_interpreted_for_other_providers(monkeypatch):
    error = ProviderFailure(details={"details": [retry_info("40s")]})
    _, clock, _, run = runner(monkeypatch, [error, "ok"], provider="openai")
    assert run()[0] == "ok"
    assert sum(clock.sleeps) == pytest.approx(2.0)


@pytest.mark.parametrize("hint,deadline", [("61", 120), ("5", 4), ("4", 4), ("86400", 120)])
def test_excessive_or_unaffordable_hint_does_not_sleep_or_retry(monkeypatch, hint, deadline):
    error = ProviderFailure(headers={"Retry-After": hint})
    manager, clock, calls, run = runner(
        monkeypatch, [error, "must not call"], deadline_seconds=deadline
    )
    with pytest.raises(RuntimeError) as raised:
        run()
    assert raised.value.__cause__ is error
    assert len(calls) == manager._attempt_count == 1
    assert not clock.sleeps
    assert clock.now == 100.0


def test_cancellation_interrupts_backoff_without_spending_another_attempt(monkeypatch):
    class Cancelled(Exception):
        pass

    manager, clock, calls, run = runner(monkeypatch, [ProviderFailure(), "must not call"])

    def cancel():
        if clock.sleeps:
            raise Cancelled()

    manager.cancel_check = cancel
    with pytest.raises(Cancelled):
        run()
    assert sum(clock.sleeps) <= 0.1
    assert len(calls) == manager._attempt_count == 1


def test_long_provider_hint_can_use_explicitly_configured_fallback(monkeypatch):
    error = ProviderFailure(headers={"Retry-After": "86400"})
    manager, clock, calls, run = runner(monkeypatch, [error, "fallback ok"])
    manager.config = manager.config.model_copy(update={"fallback_providers": ["openai"]})
    text, metadata = run()
    assert text == "fallback ok"
    assert metadata["fallback_used"]
    assert calls == [("gemini", 100.0), ("openai", 100.0)]
    assert manager._attempt_count == 2
    assert not clock.sleeps


def test_deadline_expiring_during_wait_never_starts_another_attempt(monkeypatch):
    manager, clock, calls, run = runner(monkeypatch, [ProviderFailure(), "must not call"])
    clock.after_sleep = lambda: setattr(clock, "now", 221.0)
    with pytest.raises(BudgetExceeded):
        run()
    assert len(calls) == manager._attempt_count == 1
    assert len(clock.sleeps) == 1
    assert manager.config.budget.deadline_seconds == 120


def test_attempt_budget_is_checked_before_waiting(monkeypatch):
    manager, clock, calls, run = runner(
        monkeypatch, [ProviderFailure(), "must not call"], max_llm_calls=1
    )
    with pytest.raises(BudgetExceeded):
        run()
    assert len(calls) == manager._attempt_count == 1
    assert not clock.sleeps


def test_exhausted_retry_limit_does_not_sleep_or_loop(monkeypatch):
    manager, clock, calls, run = runner(
        monkeypatch, [ProviderFailure(), ProviderFailure(), "extra"]
    )
    with pytest.raises(RuntimeError):
        run()
    assert len(calls) == manager._attempt_count == 2
    assert sum(clock.sleeps) == pytest.approx(2.0)


def test_provider_metadata_and_error_body_never_enter_logs_or_attempts(monkeypatch, caplog):
    error = ProviderFailure(
        headers={"Retry-After": "0.5", "PRIVATE_HEADER": "PRIVATE_KEY"},
        details={"error": {"details": [retry_info("1s")], "message": "PRIVATE_BODY"}},
    )
    manager, _, _, run = runner(monkeypatch, [error, "ok"])
    with caplog.at_level(logging.INFO):
        assert run()[0] == "ok"
    assert "PRIVATE_" not in caplog.text
    assert "PRIVATE_" not in json.dumps(manager.calls)
