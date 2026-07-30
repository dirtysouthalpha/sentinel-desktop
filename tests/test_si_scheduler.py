"""Tests for the self-improvement and Empire scheduler integration.

Verifies that the zero-arg scheduled task entry points run the
SelfImprovementLoop and Empire handlers, and log their results.
"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from core.mesh.si_scheduler import run_scheduled_empire, run_scheduled_si


# ---------------------------------------------------------------------------
# Self-improvement scheduled task
# ---------------------------------------------------------------------------


class TestRunScheduledSI:
    """run_scheduled_si() runs the full audit cycle and returns a summary."""

    def test_returns_summary_string(self, caplog):
        caplog.set_level(logging.INFO)
        with patch("core.mesh.self_improvement.SelfImprovementLoop") as mock_cls:
            instance = mock_cls.return_value
            instance.run.return_value = type(
                "R", (), {"summary": "Audit: 5 findings, 3 proposals, 1 executed, 1 verified"}
            )()
            result = run_scheduled_si()
        assert "findings" in result
        mock_cls.assert_called_once()

    def test_logs_start_and_summary(self, caplog):
        caplog.set_level(logging.INFO)
        with patch("core.mesh.self_improvement.SelfImprovementLoop") as mock_cls:
            instance = mock_cls.return_value
            instance.run.return_value = type("R", (), {"summary": "ok"})()
            run_scheduled_si()
        assert any("self-improvement" in r.message.lower() for r in caplog.records)

    def test_uses_project_root(self):
        with patch("core.mesh.self_improvement.SelfImprovementLoop") as mock_cls:
            instance = mock_cls.return_value
            instance.run.return_value = type("R", (), {"summary": "ok"})()
            run_scheduled_si()
        call_args = mock_cls.call_args
        assert call_args[0][0]  # non-empty path string


# ---------------------------------------------------------------------------
# Empire scheduled task
# ---------------------------------------------------------------------------


class TestRunScheduledEmpire:
    """run_scheduled_empire() runs Empire metrics and returns a summary."""

    def test_returns_summary_string(self, caplog):
        caplog.set_level(logging.INFO)
        with patch("core.mesh.empire_tasks.handle_empire_score") as mock_score, \
             patch("core.mesh.empire_tasks.handle_yt_stats") as mock_yt, \
             patch("core.mesh.empire_tasks.handle_alpaca_pnl") as mock_alpaca, \
             patch("core.mesh.empire_tasks.handle_buffer_metrics") as mock_buf:
            mock_yt.return_value = {}
            mock_alpaca.return_value = {}
            mock_buf.return_value = {}
            mock_score.return_value = {"total_score": 42}
            result = run_scheduled_empire()
        assert "42" in result

    def test_logs_result(self, caplog):
        caplog.set_level(logging.INFO)
        with patch("core.mesh.empire_tasks.handle_empire_score") as mock_score, \
             patch("core.mesh.empire_tasks.handle_yt_stats") as mock_yt, \
             patch("core.mesh.empire_tasks.handle_alpaca_pnl") as mock_alpaca, \
             patch("core.mesh.empire_tasks.handle_buffer_metrics") as mock_buf:
            mock_yt.return_value = {}
            mock_alpaca.return_value = {}
            mock_buf.return_value = {}
            mock_score.return_value = {"total_score": 0}
            run_scheduled_empire()
        assert any("empire" in r.message.lower() for r in caplog.records)

    def test_calls_all_handlers(self):
        with patch("core.mesh.empire_tasks.handle_empire_score") as mock_score, \
             patch("core.mesh.empire_tasks.handle_yt_stats") as mock_yt, \
             patch("core.mesh.empire_tasks.handle_alpaca_pnl") as mock_alpaca, \
             patch("core.mesh.empire_tasks.handle_buffer_metrics") as mock_buf:
            mock_yt.return_value = {}
            mock_alpaca.return_value = {}
            mock_buf.return_value = {}
            mock_score.return_value = {"total_score": 10}
            run_scheduled_empire()
        mock_yt.assert_called_once()
        mock_alpaca.assert_called_once()
        mock_buf.assert_called_once()
        mock_score.assert_called_once()
