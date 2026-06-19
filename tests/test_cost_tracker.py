"""Tests for core/cost_tracker.py (v21 cost tracker)."""

from __future__ import annotations

import json

import pytest

from core.cost_tracker import CostTracker, UsageRecord, get_cost_tracker


@pytest.fixture()
def tracker(tmp_path) -> CostTracker:
    return CostTracker(history_path=tmp_path / "cost_history.jsonl")


class TestUsageRecord:
    def test_to_dict_roundtrip(self):
        rec = UsageRecord(
            provider="openai",
            model="gpt-4o",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            cost_usd=0.00125,
            timestamp="2026-06-19T00:00:00+00:00",
        )
        d = rec.to_dict()
        assert d["provider"] == "openai"
        assert d["model"] == "gpt-4o"
        assert d["total_tokens"] == 150
        assert d["cost_usd"] == pytest.approx(0.00125)


class TestCostTrackerRecord:
    def test_openai_usage_fields(self, tracker):
        usage = {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
        rec = tracker.record("openai", "gpt-4o", usage)
        assert isinstance(rec, UsageRecord)
        assert rec.prompt_tokens == 1000
        assert rec.completion_tokens == 500
        assert rec.total_tokens == 1500
        assert rec.cost_usd > 0

    def test_anthropic_usage_fields(self, tracker):
        usage = {"input_tokens": 1000, "output_tokens": 500}
        rec = tracker.record("anthropic", "claude-sonnet-4-6", usage)
        assert rec.prompt_tokens == 1000
        assert rec.completion_tokens == 500
        assert rec.total_tokens == 1500
        assert rec.cost_usd > 0

    def test_unknown_model_zero_cost(self, tracker):
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        rec = tracker.record("openai", "gpt-99-future", usage)
        assert rec.cost_usd == 0.0

    def test_empty_usage_dict(self, tracker):
        rec = tracker.record("openai", "gpt-4o", {})
        assert rec.prompt_tokens == 0
        assert rec.completion_tokens == 0
        assert rec.total_tokens == 0
        assert rec.cost_usd == 0.0

    def test_run_id_attached(self, tracker):
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        rec = tracker.record("openai", "gpt-4o", usage, run_id="run-123")
        assert rec.run_id == "run-123"

    def test_persisted_to_jsonl(self, tracker, tmp_path):
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        tracker.record("openai", "gpt-4o", usage)
        history_file = tmp_path / "cost_history.jsonl"
        assert history_file.exists()
        lines = history_file.read_text().splitlines()
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["provider"] == "openai"


class TestCostTrackerSessionSummary:
    def test_empty_summary(self, tracker):
        summary = tracker.session_summary()
        assert summary["total_tokens"] == 0
        assert summary["total_cost_usd"] == 0.0
        assert summary["total_calls"] == 0

    def test_summary_accumulates(self, tracker):
        usage1 = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        usage2 = {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300}
        tracker.record("openai", "gpt-4o", usage1)
        tracker.record("openai", "gpt-4o", usage2)
        summary = tracker.session_summary()
        assert summary["total_calls"] == 2
        assert summary["total_tokens"] == 450
        assert summary["total_cost_usd"] > 0


class TestCostTrackerHistory:
    def test_history_returns_list(self, tracker):
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        tracker.record("openai", "gpt-4o", usage)
        history = tracker.history(limit=10)
        assert isinstance(history, list)
        assert len(history) == 1
        assert history[0]["provider"] == "openai"

    def test_history_limit(self, tracker):
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        for _ in range(5):
            tracker.record("openai", "gpt-4o", usage)
        history = tracker.history(limit=3)
        assert len(history) == 3

    def test_history_empty_when_no_file(self, tmp_path):
        tracker = CostTracker(history_path=tmp_path / "nonexistent.jsonl")
        assert tracker.history() == []


class TestCostTrackerReset:
    def test_reset_clears_session(self, tracker):
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        tracker.record("openai", "gpt-4o", usage)
        assert tracker.session_summary()["total_calls"] == 1
        tracker.reset_session()
        summary = tracker.session_summary()
        assert summary["total_calls"] == 0
        assert summary["total_tokens"] == 0

    def test_reset_does_not_delete_history_file(self, tracker, tmp_path):
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        tracker.record("openai", "gpt-4o", usage)
        tracker.reset_session()
        assert (tmp_path / "cost_history.jsonl").exists()


class TestGetCostTracker:
    def test_returns_singleton(self):
        t1 = get_cost_tracker()
        t2 = get_cost_tracker()
        assert t1 is t2

    def test_singleton_is_cost_tracker(self):
        assert isinstance(get_cost_tracker(), CostTracker)
