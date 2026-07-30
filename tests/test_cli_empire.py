"""Tests for the `fleet empire <action>` CLI command.

Verifies that the empire subcommand dispatches to the correct handler for
each action, produces valid text and JSON output, and handles invalid input.
"""
from __future__ import annotations

import json

import pytest

from core.mesh.cli import main


class TestCLIEmpire:
    """CLI empire command tests."""

    def test_all_text(self):
        """`empire all` prints the full analytics plan."""
        output = main(["empire", "all"])
        assert "EMPIRE ANALYTICS PLAN" in output
        assert "Empire Score:" in output
        assert "Narrative:" in output

    def test_all_json(self):
        """`empire all --format json` returns valid JSON with score and narrative."""
        output = main(["empire", "all", "--format", "json"])
        data = json.loads(output)
        assert "empire_score" in data
        assert "components" in data
        assert "narrative" in data

    def test_score_text(self):
        """`empire score` runs the score handler and prints output."""
        output = main(["empire", "score"])
        assert isinstance(output, str)
        assert len(output) > 0

    def test_score_json(self):
        """`empire score --format json` returns a total_score and components."""
        output = main(["empire", "score", "--format", "json"])
        data = json.loads(output)
        assert "total_score" in data
        assert "components" in data

    def test_yt_stats_json(self):
        """`empire yt-stats` returns views/subscribers metrics."""
        output = main(["empire", "yt-stats", "--format", "json"])
        data = json.loads(output)
        assert "views" in data
        assert "subscribers" in data

    def test_alpaca_pnl_json(self):
        """`empire alpaca-pnl` returns equity and P&L."""
        output = main(["empire", "alpaca-pnl", "--format", "json"])
        data = json.loads(output)
        assert "equity" in data
        assert "unrealized_pl" in data

    def test_buffer_metrics_json(self):
        """`empire buffer-metrics` returns post metrics."""
        output = main(["empire", "buffer-metrics", "--format", "json"])
        data = json.loads(output)
        assert "posts" in data

    def test_narrative_json(self):
        """`empire narrative` returns a generated narrative."""
        output = main(["empire", "narrative", "--format", "json"])
        data = json.loads(output)
        assert "narrative" in data

    def test_default_action_is_all(self):
        """`empire` with no action defaults to `all`."""
        output = main(["empire"])
        assert "EMPIRE ANALYTICS PLAN" in output

    def test_days_flag_accepted(self):
        """--days flag is accepted for yt-stats."""
        output = main(["empire", "yt-stats", "--days", "14"])
        assert isinstance(output, str)

    def test_invalid_action_handled(self):
        """An invalid action returns a helpful message rather than crashing.

        argparse raises SystemExit(2) for an invalid choice; the CLI wrapper
        catches it and returns a friendly string.
        """
        output = main(["empire", "nonexistent-action"])
        assert isinstance(output, str)
        assert len(output) > 0

    def test_help_does_not_crash(self):
        """empire --help exits cleanly."""
        with pytest.raises(SystemExit) as exc_info:
            main(["empire", "--help"])
        assert exc_info.value.code == 0
