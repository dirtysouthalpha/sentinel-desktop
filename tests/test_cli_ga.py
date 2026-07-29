"""Tests for CLI 1.0 GA commands (empire, audit, evals, version).

Verifies that the new CLI subcommands dispatch correctly and produce
valid output in both text and JSON formats.
"""
from __future__ import annotations

import json

import pytest

from core.mesh.cli import main


class TestCLIGACommands:
    """CLI 1.0 GA command tests."""

    def test_version_text(self):
        output = main(["version"])
        assert "Sentinel Fleet Mesh v" in output
        assert "CLI: 1.0.0" in output

    def test_empire_text(self):
        output = main(["empire"])
        assert "EMPIRE ANALYTICS PLAN" in output
        assert "Empire Score:" in output
        assert "Narrative:" in output

    def test_empire_json(self):
        output = main(["empire", "--format", "json"])
        data = json.loads(output)
        assert "empire_score" in data
        assert "components" in data
        assert "narrative" in data

    def test_evals_text(self):
        output = main(["evals"])
        assert "Golden Eval Report" in output
        assert "Total:" in output

    def test_evals_json(self):
        output = main(["evals", "--format", "json"])
        data = json.loads(output)
        assert "total" in data
        assert "pass_rate" in data
        assert isinstance(data["results"], list)

    def test_audit_text(self):
        output = main(["audit"])
        assert "SELF-IMPROVEMENT AUDIT" in output
        assert "findings" in output.lower()

    def test_audit_json(self):
        output = main(["audit", "--format", "json"])
        data = json.loads(output)
        assert "findings" in data
        assert "proposals" in data

    def test_status_still_works(self):
        """Existing status command not broken."""
        output = main(["status"])
        assert isinstance(output, str)

    def test_help_does_not_crash(self):
        """--help exits cleanly."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_unknown_command_handled(self):
        """Unknown subcommand returns helpful message."""
        output = main(["nonexistent-command-xyz"])
        assert "Unknown" in output or output == ""
