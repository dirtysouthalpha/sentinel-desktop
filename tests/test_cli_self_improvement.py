"""Tests for the `fleet self-improvement` CLI command.

Verifies that the self-improvement subcommand dispatches correctly, produces
valid output in text and JSON formats, and honors the --root flag.
"""
from __future__ import annotations

import json

import pytest

from core.mesh.cli import main


class TestCLISelfImprovement:
    """CLI self-improvement command tests."""

    def test_text_output(self):
        """Default text mode prints the audit header and summary."""
        output = main(["self-improvement"])
        assert "SELF-IMPROVEMENT AUDIT" in output
        assert "findings" in output.lower()
        assert "proposals" in output.lower()

    def test_json_output(self):
        """--format json produces valid JSON with full report structure."""
        output = main(["self-improvement", "--format", "json"])
        data = json.loads(output)
        assert "findings" in data
        assert "proposals" in data
        assert "executed" in data
        assert "verified" in data
        assert "summary" in data
        # findings and proposals are lists of dicts.
        assert isinstance(data["findings"], list)
        assert isinstance(data["proposals"], list)
        assert isinstance(data["executed"], list)
        assert isinstance(data["verified"], list)

    def test_json_findings_have_severity(self):
        """Each finding in JSON output carries a severity field."""
        output = main(["self-improvement", "--format", "json"])
        data = json.loads(output)
        if data["findings"]:
            assert "severity" in data["findings"][0]
            assert "file_path" in data["findings"][0]

    def test_root_flag(self):
        """--root flag is accepted and produces output."""
        output = main(["self-improvement", "--root", "."])
        assert "SELF-IMPROVEMENT AUDIT" in output

    def test_root_and_json(self):
        """--root combined with --format json yields valid JSON."""
        output = main(["self-improvement", "--root", ".", "--format", "json"])
        data = json.loads(output)
        assert "summary" in data

    def test_text_lists_findings_by_severity(self):
        """Text output includes severity-ranked findings."""
        output = main(["self-improvement", "--root", "."])
        # Should contain at least one severity bracket.
        assert "[" in output and "]" in output

    def test_help_does_not_crash(self):
        """self-improvement --help exits cleanly."""
        with pytest.raises(SystemExit) as exc_info:
            main(["self-improvement", "--help"])
        assert exc_info.value.code == 0
