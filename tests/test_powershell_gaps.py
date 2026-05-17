"""Gap tests for powershell.py — _run, helpers, escape, allow_raw, non-Windows paths."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from core.powershell import (
    PowerShellRunner,
    PSResult,
    _non_windows_result,
    _ps_escape_single_quoted,
    get_default_runner,
)


class TestPsEscapeSingleQuoted:
    """_ps_escape_single_quoted edge cases."""

    def test_basic_string(self):
        assert _ps_escape_single_quoted("hello") == "'hello'"

    def test_embedded_quote(self):
        assert _ps_escape_single_quoted("it's") == "'it''s'"

    def test_empty_string(self):
        assert _ps_escape_single_quoted("") == "''"

    def test_non_string_raises_type_error(self):
        with pytest.raises(TypeError, match="expected str"):
            _ps_escape_single_quoted(42)

    def test_null_char_raises_value_error(self):
        with pytest.raises(ValueError, match="control character"):
            _ps_escape_single_quoted("hello\x00world")

    def test_newline_raises_value_error(self):
        with pytest.raises(ValueError, match="control character"):
            _ps_escape_single_quoted("line1\nline2")

    def test_carriage_return_raises_value_error(self):
        with pytest.raises(ValueError, match="control character"):
            _ps_escape_single_quoted("line1\rline2")


class TestNonWindowsResult:
    """_non_windows_result returns appropriate PSResult."""

    def test_returns_fail_result(self):
        result = _non_windows_result()
        assert result.success is False
        assert result.exit_code == -1
        assert "only supported on Windows" in result.stderr
        assert result.objects == []


class TestResolvePsExe:
    """_resolve_ps_exe on non-Windows and error paths."""

    @patch("core.powershell._is_windows", return_value=False)
    def test_non_windows_returns_powershell_exe(self, mock_iw):
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner._resolve_ps_exe()
        assert result == "powershell.exe"

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_where_finds_pwsh(self, mock_run, mock_iw):
        mock_run.return_value = MagicMock(returncode=0, stdout="C:\\pwsh.exe\n")
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner._resolve_ps_exe()
        assert result == "pwsh.exe"

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_where_finds_powershell(self, mock_run, mock_iw):
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout=""),
            MagicMock(returncode=0, stdout="C:\\powershell.exe\n"),
        ]
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner._resolve_ps_exe()
        assert result == "powershell.exe"

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run", side_effect=OSError("not found"))
    def test_where_all_fail_falls_back(self, mock_run, mock_iw):
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner._resolve_ps_exe()
        assert result == "powershell.exe"


class TestParseJsonOutput:
    """_parse_json_output edge cases."""

    def test_empty_string(self):
        assert PowerShellRunner._parse_json_output("") == []

    def test_whitespace_only(self):
        assert PowerShellRunner._parse_json_output("  \n  ") == []

    def test_single_object(self):
        data = '{"Name": "test", "Status": "Running"}'
        result = PowerShellRunner._parse_json_output(data)
        assert len(result) == 1
        assert result[0]["Name"] == "test"

    def test_array_of_objects(self):
        data = '[{"A": 1}, {"B": 2}]'
        result = PowerShellRunner._parse_json_output(data)
        assert len(result) == 2

    def test_scalar_value(self):
        data = '"hello"'
        result = PowerShellRunner._parse_json_output(data)
        assert result == [{"value": "hello"}]

    def test_number_value(self):
        data = "42"
        result = PowerShellRunner._parse_json_output(data)
        assert result == [{"value": 42}]

    def test_invalid_json(self):
        data = "not valid json {"
        result = PowerShellRunner._parse_json_output(data)
        assert result == []


class TestBuildEnv:
    """_build_env merges custom vars."""

    def test_custom_vars_added(self):
        runner = PowerShellRunner.__new__(PowerShellRunner)
        runner.env_vars = {"MY_VAR": "42"}
        env = runner._build_env()
        assert env["MY_VAR"] == "42"


class TestBaseArgs:
    """_base_args includes exe and flags."""

    def test_base_args(self):
        runner = PowerShellRunner.__new__(PowerShellRunner)
        runner._ps_exe = "pwsh.exe"
        args = runner._base_args()
        assert args[0] == "pwsh.exe"
        assert "-NoProfile" in args
        assert "-NonInteractive" in args


class TestRunNonWindows:
    """_run on non-Windows returns error result."""

    @patch("core.powershell._is_windows", return_value=False)
    def test_returns_non_windows_result(self, mock_iw):
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner._run("Get-Date")
        assert result.success is False
        assert result.exit_code == -1


class TestRunSuccess:
    """_run with mocked subprocess."""

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_successful_run(self, mock_run, mock_iw):
        mock_proc = MagicMock(
            returncode=0,
            stdout='{"Name":"test","Status":"Running"}',
            stderr="",
        )
        mock_run.return_value = mock_proc
        runner = PowerShellRunner.__new__(PowerShellRunner)
        runner._ps_exe = "powershell.exe"
        runner.timeout = 30
        runner.working_dir = "."
        runner.run_as_admin = False
        runner.env_vars = {}
        result = runner._run("Get-Service test")
        assert result.success is True
        assert result.exit_code == 0
        assert len(result.objects) == 1
        assert result.objects[0]["Name"] == "test"

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_failed_exit_code(self, mock_run, mock_iw):
        mock_proc = MagicMock(returncode=1, stdout="", stderr="access denied")
        mock_run.return_value = mock_proc
        runner = PowerShellRunner.__new__(PowerShellRunner)
        runner._ps_exe = "powershell.exe"
        runner.timeout = 30
        runner.working_dir = "."
        runner.run_as_admin = False
        runner.env_vars = {}
        result = runner._run("Get-Service nosuch")
        assert result.success is False
        assert result.exit_code == 1

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_timeout_expired(self, mock_run, mock_iw):
        import subprocess as real_sub

        mock_run.side_effect = real_sub.TimeoutExpired(cmd="ps", timeout=30)
        runner = PowerShellRunner.__new__(PowerShellRunner)
        runner._ps_exe = "powershell.exe"
        runner.timeout = 30
        runner.working_dir = "."
        runner.run_as_admin = False
        runner.env_vars = {}
        result = runner._run("long-running")
        assert result.success is False
        assert result.exit_code == -2

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_file_not_found(self, mock_run, mock_iw):
        mock_run.side_effect = FileNotFoundError("no powershell")
        runner = PowerShellRunner.__new__(PowerShellRunner)
        runner._ps_exe = "missing.exe"
        runner.timeout = 30
        runner.working_dir = "."
        runner.run_as_admin = False
        runner.env_vars = {}
        result = runner._run("Get-Date")
        assert result.success is False
        assert result.exit_code == -3

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_generic_exception(self, mock_run, mock_iw):
        mock_run.side_effect = RuntimeError("unexpected")
        runner = PowerShellRunner.__new__(PowerShellRunner)
        runner._ps_exe = "powershell.exe"
        runner.timeout = 30
        runner.working_dir = "."
        runner.run_as_admin = False
        runner.env_vars = {}
        result = runner._run("Get-Date")
        assert result.success is False
        assert result.exit_code == -4


class TestRunScriptNotFound:
    """run_script with missing file."""

    def test_script_not_found(self):
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.run_script("/nonexistent/script.ps1")
        assert result.success is False
        assert "Script not found" in result.stderr


class TestRunCommandAllowRaw:
    """run_command with allow_raw=False."""

    def test_refused_when_raw_disabled(self):
        runner = PowerShellRunner.__new__(PowerShellRunner)
        runner.allow_raw = False
        result = runner.run_command("Get-Date")
        assert result.success is False
        assert result.exit_code == -5


class TestRunInlineAllowRaw:
    """run_inline with allow_raw=False."""

    def test_refused_when_raw_disabled(self):
        runner = PowerShellRunner.__new__(PowerShellRunner)
        runner.allow_raw = False
        result = runner.run_inline("Get-Date")
        assert result.success is False
        assert result.exit_code == -5


class TestRunInlineEscapes:
    """run_inline escapes double quotes."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific PowerShell escaping test")
    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_inline_escapes_quotes(self, mock_run, mock_iw):
        mock_proc = MagicMock(returncode=0, stdout="", stderr="")
        mock_run.return_value = mock_proc
        runner = PowerShellRunner.__new__(PowerShellRunner)
        runner._ps_exe = "powershell.exe"
        runner.timeout = 30
        runner.working_dir = "."
        runner.run_as_admin = False
        runner.env_vars = {}
        runner.allow_raw = True
        result = runner.run_inline('Write-Host "hello"')
        assert result.success is True
        args_passed = mock_run.call_args[0][0]
        assert any('\\"hello\\"' in a for a in args_passed)


class TestGetServiceStatus:
    """get_service_status helper."""

    def test_invalid_name_returns_error(self):
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.get_service_status("bad\x00name")
        assert result["Status"] == "Unknown"
        assert "invalid" in result["error"]

    def test_non_string_returns_error(self):
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.get_service_status(42)
        assert result["Status"] == "Unknown"

    @patch.object(PowerShellRunner, "_run")
    def test_successful_status(self, mock_run):
        mock_run.return_value = PSResult(
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            objects=[
                {
                    "Name": "Spooler",
                    "Status": "Running",
                    "StartType": "Automatic",
                    "DisplayName": "Print Spooler",
                }
            ],
        )
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.get_service_status("Spooler")
        assert result["Status"] == "Running"

    @patch.object(PowerShellRunner, "_run")
    def test_failed_status_returns_unknown(self, mock_run):
        mock_run.return_value = PSResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr="not found",
            objects=[],
        )
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.get_service_status("NoSuchSvc")
        assert result["Status"] == "Unknown"
        assert "not found" in result["error"]


class TestRestartService:
    """restart_service helper."""

    def test_invalid_name_returns_error(self):
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.restart_service("bad\x00name")
        assert result["Success"] is False
        assert "invalid" in result["error"]

    @patch.object(PowerShellRunner, "_run")
    def test_successful_restart(self, mock_run):
        mock_run.return_value = PSResult(
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            objects=[
                {"Name": "Spooler", "Status": "Running", "Action": "Restarted", "Success": True}
            ],
        )
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.restart_service("Spooler")
        assert result["Success"] is True

    @patch.object(PowerShellRunner, "_run")
    def test_failed_restart(self, mock_run):
        mock_run.return_value = PSResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr="access denied",
            objects=[],
        )
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.restart_service("Spooler")
        assert result["Success"] is False
        assert "access denied" in result["error"]


class TestGetEventErrors:
    """get_event_errors helper."""

    @patch.object(PowerShellRunner, "_run")
    def test_returns_objects_on_success(self, mock_run):
        mock_run.return_value = PSResult(
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            objects=[{"Id": 100, "Message": "Error event"}],
        )
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.get_event_errors(hours=2)
        assert len(result) == 1

    @patch.object(PowerShellRunner, "_run")
    def test_returns_empty_on_failure(self, mock_run):
        mock_run.return_value = PSResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr="fail",
            objects=[],
        )
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.get_event_errors()
        assert result == []


class TestGetInstalledSoftware:
    """get_installed_software helper."""

    @patch.object(PowerShellRunner, "_run")
    def test_returns_software_list(self, mock_run):
        mock_run.return_value = PSResult(
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            objects=[{"DisplayName": "Python", "DisplayVersion": "3.13"}],
        )
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.get_installed_software()
        assert len(result) == 1
        assert result[0]["DisplayName"] == "Python"


class TestGetDiskUsage:
    """get_disk_usage helper."""

    @patch.object(PowerShellRunner, "_run")
    def test_returns_disk_info(self, mock_run):
        mock_run.return_value = PSResult(
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            objects=[{"DeviceID": "C:", "TotalGB": 500.0}],
        )
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.get_disk_usage()
        assert len(result) == 1


class TestGetNetworkConfig:
    """get_network_config helper."""

    @patch.object(PowerShellRunner, "_run")
    def test_returns_network_info(self, mock_run):
        mock_run.return_value = PSResult(
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            objects=[{"Description": "Ethernet"}],
        )
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.get_network_config()
        assert len(result) == 1


class TestTestConnection:
    """test_connection helper."""

    def test_invalid_host_returns_error(self):
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.test_connection("bad\x00host")
        assert result["PingSucceeded"] is False
        assert "invalid" in result["error"]

    def test_non_string_host_returns_error(self):
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.test_connection(42)
        assert result["PingSucceeded"] is False

    @patch.object(PowerShellRunner, "_run")
    def test_successful_ping(self, mock_run):
        mock_run.return_value = PSResult(
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            objects=[{"Host": "google.com", "PingSucceeded": True, "PingMs": 12.5}],
        )
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.test_connection("google.com")
        assert result["PingSucceeded"] is True

    @patch.object(PowerShellRunner, "_run")
    def test_failed_ping(self, mock_run):
        mock_run.return_value = PSResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr="timeout",
            objects=[],
        )
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner.test_connection("unreachable")
        assert result["PingSucceeded"] is False
        assert "timeout" in result["error"]


class TestPSResultStr:
    """PSResult.__str__ formatting."""

    def test_success_str(self):
        r = PSResult(success=True, exit_code=0, stdout="ok", stderr="", objects=[{"a": 1}])
        s = str(r)
        assert "OK" in s
        assert "code=0" in s

    def test_failure_str(self):
        r = PSResult(success=False, exit_code=1, stdout="", stderr="err", objects=[])
        s = str(r)
        assert "FAIL" in s


class TestGetDefaultRunner:
    """get_default_runner lazy singleton."""

    @patch("core.powershell._default_runner", None)
    def test_creates_new_runner(self):
        import core.powershell as ps_mod

        old = ps_mod._default_runner
        ps_mod._default_runner = None
        runner = get_default_runner()
        assert isinstance(runner, PowerShellRunner)
        ps_mod._default_runner = old

    def test_returns_cached_runner(self):
        import core.powershell as ps_mod

        mock_runner = MagicMock(spec=PowerShellRunner)
        old = ps_mod._default_runner
        ps_mod._default_runner = mock_runner
        result = get_default_runner()
        assert result is mock_runner
        ps_mod._default_runner = old
