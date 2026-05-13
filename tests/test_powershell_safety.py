"""Tests for PowerShell argument escaping and the ``allow_raw`` gate.

These tests do NOT execute PowerShell — they assert that the helper
functions and high-level methods refuse or escape dangerous inputs
before any subprocess is spawned.
"""

import pytest

from core import powershell
from core.powershell import PowerShellRunner, _ps_escape_single_quoted

# ---------------------------------------------------------------------------
# _ps_escape_single_quoted
# ---------------------------------------------------------------------------


def test_escape_basic():
    assert _ps_escape_single_quoted("Spooler") == "'Spooler'"


def test_escape_doubles_single_quotes():
    """PowerShell single-quote escape is double-quote: ``'foo''bar'``."""
    assert _ps_escape_single_quoted("foo'bar") == "'foo''bar'"


def test_escape_injection_payload():
    payload = "Spooler'; Stop-Computer; '"
    out = _ps_escape_single_quoted(payload)
    # The payload's single quotes must be doubled so PS sees them as data.
    assert out == "'Spooler''; Stop-Computer; '''"
    # And the result must not contain an unescaped ``'`` that would close.
    assert out.startswith("'") and out.endswith("'")


def test_escape_rejects_newlines():
    with pytest.raises(ValueError):
        _ps_escape_single_quoted("foo\nbar")


def test_escape_rejects_carriage_return():
    with pytest.raises(ValueError):
        _ps_escape_single_quoted("foo\rbar")


def test_escape_rejects_nul():
    with pytest.raises(ValueError):
        _ps_escape_single_quoted("foo\x00bar")


def test_escape_rejects_non_string():
    with pytest.raises(TypeError):
        _ps_escape_single_quoted(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# allow_raw gate
# ---------------------------------------------------------------------------


def test_run_command_refuses_when_allow_raw_false(monkeypatch):
    """``allow_raw=False`` blocks the raw command surface before subprocess."""
    runner = PowerShellRunner(allow_raw=False)

    # Sentinel: if subprocess is reached, we explode the test.
    def _fail(*a, **kw):
        raise AssertionError("subprocess should not be invoked when allow_raw=False")

    monkeypatch.setattr(powershell.subprocess, "run", _fail)

    result = runner.run_command("Get-Process")
    assert result.success is False
    assert "allow_raw=False" in result.stderr


def test_run_inline_refuses_when_allow_raw_false(monkeypatch):
    runner = PowerShellRunner(allow_raw=False)
    monkeypatch.setattr(
        powershell.subprocess,
        "run",
        lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("subprocess should not be invoked when allow_raw=False")
        ),
    )
    result = runner.run_inline("$x = 1")
    assert result.success is False
    assert "allow_raw=False" in result.stderr


def test_allow_raw_default_is_true():
    """Backwards-compatible default: existing callers keep current behavior."""
    runner = PowerShellRunner()
    assert runner.allow_raw is True


# ---------------------------------------------------------------------------
# Helper APIs reject malformed names before building command strings.
# ---------------------------------------------------------------------------


def test_get_service_status_rejects_newline_name():
    runner = PowerShellRunner()
    out = runner.get_service_status("Spooler\nattack")
    assert out["error"].startswith("invalid service name")


def test_restart_service_rejects_newline_name():
    runner = PowerShellRunner()
    out = runner.restart_service("Spooler\nattack")
    assert out["Success"] is False
    assert "invalid service name" in out["error"]


def test_test_connection_rejects_newline_host():
    runner = PowerShellRunner()
    out = runner.test_connection("evil.example.com\nattack")
    assert out["PingSucceeded"] is False
    assert "invalid host" in out["error"]
