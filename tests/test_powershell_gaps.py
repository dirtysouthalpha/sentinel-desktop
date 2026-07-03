"""Gap-filling tests for core/powershell.py.

Covers PowerShellRunner internals (_run on Linux, _resolve_ps_exe, _build_env,
_base_args), public API methods (run_script with args, run_command, run_inline),
built-in helpers on non-Windows, PSResult edge cases, and the module-level
get_default_runner() factory.
"""

import sys
from unittest.mock import patch

import pytest

from core.powershell import (
    PowerShellRunner,
    PSResult,
    _is_windows,
    _non_windows_result,
    _ps_escape_single_quoted,
    get_default_runner,
)

# ---------------------------------------------------------------------------
# _is_windows / _non_windows_result
# ---------------------------------------------------------------------------


class TestPlatformHelpers:
    @pytest.mark.skipif(
        sys.platform == "win32", reason="Asserts _is_windows() is False (Linux-only)"
    )
    def test_is_windows_on_linux(self):
        assert _is_windows() is False

    def test_non_windows_result(self):
        r = _non_windows_result()
        assert r.success is False
        assert r.exit_code == -1
        assert "only supported on Windows" in r.stderr
        assert r.objects == []


# ---------------------------------------------------------------------------
# PSResult edge cases
# ---------------------------------------------------------------------------


class TestPSResultGaps:
    def test_str_with_empty_stdout(self):
        r = PSResult(success=True, exit_code=0, stdout="", stderr="", objects=[])
        s = str(r)
        assert "OK" in s
        assert "0c" in s

    def test_str_with_many_objects(self):
        r = PSResult(
            success=True,
            exit_code=0,
            stdout="x",
            stderr="",
            objects=[{"a": i} for i in range(10)],
        )
        s = str(r)
        assert "objects=10" in s

    def test_ps_result_fields(self):
        r = PSResult(success=False, exit_code=42, stdout="out", stderr="err", objects=[{"k": "v"}])
        assert r.success is False
        assert r.exit_code == 42
        assert r.stdout == "out"
        assert r.stderr == "err"
        assert len(r.objects) == 1


# ---------------------------------------------------------------------------
# PowerShellRunner internals
# ---------------------------------------------------------------------------


class TestRunnerInit:
    def test_default_params(self):
        runner = PowerShellRunner()
        assert runner.timeout == 300
        assert runner.run_as_admin is False
        assert runner.allow_raw is True
        assert runner.env_vars == {}

    def test_custom_params(self):
        runner = PowerShellRunner(
            timeout=60, run_as_admin=True, working_dir="/tmp", env_vars={"FOO": "bar"}, allow_raw=False
        )
        assert runner.timeout == 60
        assert runner.run_as_admin is True
        assert runner.working_dir == "/tmp"
        assert runner.env_vars == {"FOO": "bar"}
        assert runner.allow_raw is False


class TestRunnerInternals:
    def test_resolve_ps_exe_on_linux(self):
        runner = PowerShellRunner()
        assert runner._ps_exe == "powershell.exe"

    def test_build_env_includes_custom_vars(self):
        runner = PowerShellRunner(env_vars={"MY_VAR": "test"})
        env = runner._build_env()
        assert env["MY_VAR"] == "test"

    def test_build_env_preserves_existing(self):
        runner = PowerShellRunner()
        env = runner._build_env()
        assert "PATH" in env or "path" in env

    def test_base_args_structure(self):
        runner = PowerShellRunner()
        args = runner._base_args()
        assert args[0] == "powershell.exe"
        assert "-NoProfile" in args
        assert "-NonInteractive" in args
        # -OutputFormat was removed (PS rejects "JSON" as a format value; JSON
        # conversion is handled by ConvertTo-Json in the command itself).
        assert not any(a.startswith("-OutputFormat") for a in args)
        assert "JSON" not in args


# ---------------------------------------------------------------------------
# _run on non-Windows (always returns non-windows result)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform == "win32", reason="Tests Linux-only early-return path"
)
class TestRunOnLinux:
    """These tests verify the non-Windows early-return path. They must NOT
    run on Windows, where _run() would actually execute PowerShell commands."""

    def test_run_returns_non_windows_result(self):
        runner = PowerShellRunner()
        result = runner._run("Get-Process")
        assert result.success is False
        assert "only supported on Windows" in result.stderr

    def test_run_command_on_linux(self):
        runner = PowerShellRunner(allow_raw=True)
        result = runner.run_command("Get-Process")
        assert result.success is False

    def test_run_inline_on_linux(self):
        runner = PowerShellRunner(allow_raw=True)
        result = runner.run_inline("Get-Process | Select -First 1")
        assert result.success is False


# ---------------------------------------------------------------------------
# run_script gaps
# ---------------------------------------------------------------------------


class TestRunScriptGaps:
    def test_run_script_with_args(self, tmp_path):
        """run_script should build parameter string from args dict."""
        runner = PowerShellRunner()
        script = tmp_path / "test.ps1"
        script.write_text('Write-Output "hello"')

        with patch.object(runner, "_run") as mock_run:
            mock_run.return_value = PSResult(success=True, exit_code=0, stdout="hello", stderr="", objects=[])
            result = runner.run_script(str(script), args={"Name": "Test", "Count": 5})
            assert result.success is True
            # Verify _run was called with the script path and params
            call_args = mock_run.call_args[0][0]
            assert str(script) in call_args
            assert "-Name" in call_args
            assert "-Count" in call_args

    def test_run_script_with_bad_arg_value(self, tmp_path):
        """run_script should handle un-escapable arg values gracefully."""
        runner = PowerShellRunner()
        script = tmp_path / "test.ps1"
        script.write_text('Write-Output "hello"')

        with patch.object(runner, "_run") as mock_run:
            mock_run.return_value = PSResult(success=True, exit_code=0, stdout="ok", stderr="", objects=[])
            # Value with null byte → _ps_escape raises ValueError → falls back to ''
            runner.run_script(str(script), args={"Key": "bad\x00val"})
            call_args = mock_run.call_args[0][0]
            assert "-Key ''" in call_args


# ---------------------------------------------------------------------------
# Built-in helpers on non-Windows
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform == "win32", reason="Tests non-Windows fallback behavior"
)
class TestBuiltInHelpersOnLinux:
    def test_get_event_errors(self):
        runner = PowerShellRunner()
        result = runner.get_event_errors(hours=2)
        assert result == []

    def test_get_installed_software(self):
        runner = PowerShellRunner()
        result = runner.get_installed_software()
        assert result == []

    def test_get_disk_usage(self):
        runner = PowerShellRunner()
        result = runner.get_disk_usage()
        assert result == []

    def test_get_network_config(self):
        runner = PowerShellRunner()
        result = runner.get_network_config()
        assert result == []

    def test_get_service_status_on_linux(self):
        runner = PowerShellRunner()
        result = runner.get_service_status("Spooler")
        assert result["Status"] == "Unknown"

    def test_restart_service_on_linux(self):
        runner = PowerShellRunner()
        result = runner.restart_service("Spooler")
        assert result["Success"] is False

    def test_test_connection_on_linux(self):
        runner = PowerShellRunner()
        result = runner.test_connection("localhost")
        assert result["PingSucceeded"] is False


# ---------------------------------------------------------------------------
# get_default_runner
# ---------------------------------------------------------------------------


class TestGetDefaultRunner:
    def test_returns_runner(self):
        runner = get_default_runner()
        assert isinstance(runner, PowerShellRunner)

    def test_returns_same_instance(self):
        import core.powershell as ps

        # Reset for clean test
        ps._default_runner = None
        r1 = get_default_runner()
        r2 = get_default_runner()
        assert r1 is r2
        # Clean up
        ps._default_runner = None


# ---------------------------------------------------------------------------
# _ps_escape_single_quoted additional edge cases
# ---------------------------------------------------------------------------


class TestPsEscapeEdgeCases:
    def test_backslash_passes_through(self):
        result = _ps_escape_single_quoted(r"C:\Windows")
        assert result == r"'C:\Windows'"

    def test_double_quotes_pass_through(self):
        result = _ps_escape_single_quoted('say "hello"')
        assert result == """'say "hello"'"""

    def test_unicode_string(self):
        result = _ps_escape_single_quoted("héllo wörld")
        assert result == "'héllo wörld'"

    def test_very_long_string(self):
        long_str = "a" * 10000
        result = _ps_escape_single_quoted(long_str)
        assert result == f"'{long_str}'"

    def test_tab_passes_through(self):
        result = _ps_escape_single_quoted("hello\tworld")
        assert result == "'hello\tworld'"
