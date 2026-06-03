"""Extended tests for core/powershell.py — runner config, helpers, JSON parsing, platform guards."""

from pathlib import Path
from unittest.mock import MagicMock, patch

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
# _ps_escape_single_quoted extended
# ---------------------------------------------------------------------------

class TestPsEscapeExtended:
    def test_unicode_string(self):
        result = _ps_escape_single_quoted("héllo wörld")
        assert result == "'héllo wörld'"

    def test_special_chars_pass_through(self):
        result = _ps_escape_single_quoted("foo$bar`baz")
        assert result == "'foo$bar`baz'"

    def test_backslash_pass_through(self):
        result = _ps_escape_single_quoted("C:\\Users\\test")
        assert result == "'C:\\Users\\test'"

    def test_double_quotes_pass_through(self):
        result = _ps_escape_single_quoted('say "hello"')
        assert result == '\'say "hello"\''

    def test_only_single_quote(self):
        assert _ps_escape_single_quoted("'") == "''''"

    def test_long_string(self):
        s = "a" * 10000
        result = _ps_escape_single_quoted(s)
        assert result == f"'{s}'"

    def test_rejects_bool(self):
        with pytest.raises(TypeError):
            _ps_escape_single_quoted(True)

    def test_rejects_none(self):
        with pytest.raises(TypeError):
            _ps_escape_single_quoted(None)

    def test_rejects_list(self):
        with pytest.raises(TypeError):
            _ps_escape_single_quoted(["not", "a", "string"])


# ---------------------------------------------------------------------------
# PSResult extended
# ---------------------------------------------------------------------------

class TestPSResultExtended:
    def test_success_with_objects(self):
        r = PSResult(
            success=True, exit_code=0,
            stdout='[{"Name": "test"}]',
            stderr="",
            objects=[{"Name": "test"}],
        )
        assert r.success is True
        assert len(r.objects) == 1
        assert r.objects[0]["Name"] == "test"

    def test_str_with_empty_stdout(self):
        r = PSResult(success=True, exit_code=0, stdout="", stderr="", objects=[])
        s = str(r)
        assert "OK" in s
        assert "0c" in s

    def test_str_with_large_stdout(self):
        r = PSResult(success=True, exit_code=0, stdout="x" * 10000, stderr="", objects=[])
        s = str(r)
        assert "10000c" in s

    def test_str_with_many_objects(self):
        r = PSResult(
            success=True, exit_code=0, stdout="",
            stderr="", objects=[{"a": i} for i in range(50)],
        )
        s = str(r)
        assert "objects=50" in s

    def test_equality(self):
        a = PSResult(success=True, exit_code=0, stdout="ok", stderr="", objects=[])
        b = PSResult(success=True, exit_code=0, stdout="ok", stderr="", objects=[])
        assert a == b

    def test_inequality(self):
        a = PSResult(success=True, exit_code=0, stdout="ok", stderr="", objects=[])
        b = PSResult(success=False, exit_code=1, stdout="ok", stderr="", objects=[])
        assert a != b


# ---------------------------------------------------------------------------
# Platform guards
# ---------------------------------------------------------------------------

class TestPlatformGuards:
    @patch("core.utils.platform.system", return_value="Linux")
    def test_is_windows_false_on_linux(self, mock_sys):
        assert _is_windows() is False

    @patch("core.utils.platform.system", return_value="Windows")
    def test_is_windows_true_on_windows(self, mock_sys):
        assert _is_windows() is True

    @patch("core.utils.platform.system", return_value="Darwin")
    def test_is_windows_false_on_mac(self, mock_sys):
        assert _is_windows() is False

    def test_non_windows_result(self):
        r = _non_windows_result()
        assert r.success is False
        assert r.exit_code == -1
        assert "Windows" in r.stderr


# ---------------------------------------------------------------------------
# PowerShellRunner initialization
# ---------------------------------------------------------------------------

class TestRunnerInit:
    def test_default_timeout(self):
        runner = PowerShellRunner()
        assert runner.timeout == 300

    def test_custom_timeout(self):
        runner = PowerShellRunner(timeout=60)
        assert runner.timeout == 60

    def test_default_allow_raw(self):
        runner = PowerShellRunner()
        assert runner.allow_raw is True

    def test_allow_raw_false(self):
        runner = PowerShellRunner(allow_raw=False)
        assert runner.allow_raw is False

    def test_run_as_admin_default(self):
        runner = PowerShellRunner()
        assert runner.run_as_admin is False

    def test_run_as_admin_true(self):
        runner = PowerShellRunner(run_as_admin=True)
        assert runner.run_as_admin is True

    def test_working_dir_default(self):
        runner = PowerShellRunner()
        assert runner.working_dir == str(Path.cwd())

    def test_custom_working_dir(self):
        runner = PowerShellRunner(working_dir="/tmp")
        assert runner.working_dir == "/tmp"

    def test_env_vars_default_empty(self):
        runner = PowerShellRunner()
        assert runner.env_vars == {}

    def test_custom_env_vars(self):
        runner = PowerShellRunner(env_vars={"FOO": "bar"})
        assert runner.env_vars == {"FOO": "bar"}

    def test_ps_exe_is_set(self):
        runner = PowerShellRunner()
        assert runner._ps_exe in ("powershell.exe", "pwsh.exe")


# ---------------------------------------------------------------------------
# _base_args
# ---------------------------------------------------------------------------

class TestBaseArgs:
    def test_includes_no_profile(self):
        runner = PowerShellRunner()
        args = runner._base_args()
        assert "-NoProfile" in args

    def test_includes_non_interactive(self):
        runner = PowerShellRunner()
        args = runner._base_args()
        assert "-NonInteractive" in args

    def test_includes_json_output(self):
        runner = PowerShellRunner()
        args = runner._base_args()
        assert "JSON" in args

    def test_starts_with_exe(self):
        runner = PowerShellRunner()
        args = runner._base_args()
        assert args[0] == runner._ps_exe


# ---------------------------------------------------------------------------
# _build_env
# ---------------------------------------------------------------------------

class TestBuildEnv:
    def test_includes_system_env(self):
        runner = PowerShellRunner()
        env = runner._build_env()
        # PATH should be present from the system environment
        assert "PATH" in env

    def test_merges_custom_vars(self):
        runner = PowerShellRunner(env_vars={"MY_VAR": "test"})
        env = runner._build_env()
        assert env["MY_VAR"] == "test"

    def test_overrides_system_var(self):
        runner = PowerShellRunner(env_vars={"PATH": "/custom"})
        env = runner._build_env()
        assert env["PATH"] == "/custom"

    def test_converts_values_to_str(self):
        runner = PowerShellRunner(env_vars={"NUM": 42})
        env = runner._build_env()
        assert env["NUM"] == "42"


# ---------------------------------------------------------------------------
# _parse_json_output extended
# ---------------------------------------------------------------------------

class TestParseJsonOutputExtended:
    def test_nested_json(self):
        data = '{"outer": {"inner": [1, 2, 3]}}'
        result = PowerShellRunner._parse_json_output(data)
        assert len(result) == 1
        assert result[0]["outer"]["inner"] == [1, 2, 3]

    def test_json_null(self):
        result = PowerShellRunner._parse_json_output("null")
        assert result == [{"value": None}]

    def test_json_boolean(self):
        result = PowerShellRunner._parse_json_output("true")
        assert result == [{"value": True}]

    def test_json_string(self):
        result = PowerShellRunner._parse_json_output('"hello"')
        assert result == [{"value": "hello"}]

    def test_json_float(self):
        result = PowerShellRunner._parse_json_output("3.14")
        assert result == [{"value": 3.14}]

    def test_mixed_content_with_json(self):
        """Leading/trailing whitespace should be stripped."""
        result = PowerShellRunner._parse_json_output('  {"a": 1}  ')
        assert result == [{"a": 1}]

    def test_multiple_json_objects_not_array(self):
        """Two JSON objects concatenated is not valid JSON."""
        result = PowerShellRunner._parse_json_output('{"a":1}{"b":2}')
        assert result == []

    def test_empty_array(self):
        result = PowerShellRunner._parse_json_output("[]")
        assert result == []

    def test_single_element_array(self):
        result = PowerShellRunner._parse_json_output('[{"x": 1}]')
        assert result == [{"x": 1}]


# ---------------------------------------------------------------------------
# _run — non-Windows path
# ---------------------------------------------------------------------------

class TestRunNonWindows:
    @patch("core.powershell._is_windows", return_value=False)
    def test_returns_non_windows_result(self, mock_win):
        runner = PowerShellRunner()
        result = runner._run("Get-Process")
        assert result.success is False
        assert result.exit_code == -1
        assert "Windows" in result.stderr


# ---------------------------------------------------------------------------
# run_script — edge cases
# ---------------------------------------------------------------------------

class TestRunScriptExtended:
    def test_nonexistent_script(self, tmp_path):
        runner = PowerShellRunner()
        result = runner.run_script(str(tmp_path / "nope.ps1"))
        assert result.success is False
        assert "not found" in result.stderr.lower()

    @patch("core.powershell._is_windows", return_value=False)
    def test_existing_script_non_windows(self, mock_win, tmp_path):
        script = tmp_path / "test.ps1"
        script.write_text('Write-Output "hello"')
        runner = PowerShellRunner()
        result = runner.run_script(str(script))
        assert result.success is False

    def test_script_with_args_escapes_values(self, tmp_path):
        """Verify that script args are properly escaped."""
        script = tmp_path / "test.ps1"
        script.write_text('param($Name) Write-Output $Name')
        runner = PowerShellRunner()
        # On Linux this will fail since PS isn't available,
        # but we can verify it doesn't crash on the escaping
        result = runner.run_script(str(script), args={"Name": "it's a test"})
        # Result depends on platform — just verify no Python exception
        assert isinstance(result, PSResult)


# ---------------------------------------------------------------------------
# run_command / run_inline — allow_raw guard
# ---------------------------------------------------------------------------

class TestRawGuard:
    def test_run_command_refused_with_allow_raw_false(self):
        runner = PowerShellRunner(allow_raw=False)
        result = runner.run_command("Get-Process")
        assert result.success is False
        assert result.exit_code == -5
        assert "allow_raw=False" in result.stderr

    def test_run_inline_refused_with_allow_raw_false(self):
        runner = PowerShellRunner(allow_raw=False)
        result = runner.run_inline("Get-Process | Select -First 1")
        assert result.success is False
        assert result.exit_code == -5
        assert "allow_raw=False" in result.stderr

    @patch("core.powershell._is_windows", return_value=False)
    def test_run_command_allowed_but_non_windows(self, mock_win):
        runner = PowerShellRunner(allow_raw=True)
        result = runner.run_command("Get-Process")
        assert result.success is False

    @patch("core.powershell._is_windows", return_value=False)
    def test_run_inline_allowed_but_non_windows(self, mock_win):
        runner = PowerShellRunner(allow_raw=True)
        result = runner.run_inline("Get-Process | Select -First 1")
        assert result.success is False


# ---------------------------------------------------------------------------
# Built-in helpers — bad input handling
# ---------------------------------------------------------------------------

class TestBuiltinHelpersBadInput:
    def test_get_service_status_empty_name(self):
        runner = PowerShellRunner()
        result = runner.get_service_status("")
        # Empty string is valid but will fail on Linux
        assert isinstance(result, dict)

    def test_get_service_status_newline_in_name(self):
        runner = PowerShellRunner()
        result = runner.get_service_status("bad\nname")
        assert result["Status"] == "Unknown"

    def test_restart_service_newline_in_name(self):
        runner = PowerShellRunner()
        result = runner.restart_service("bad\nname")
        assert result["Success"] is False

    def test_test_connection_empty_host(self):
        runner = PowerShellRunner()
        result = runner.test_connection("")
        assert isinstance(result, dict)
        assert result["Host"] == ""

    def test_test_connection_null_in_host(self):
        runner = PowerShellRunner()
        result = runner.test_connection("host\x00evil")
        assert result["PingSucceeded"] is False
        assert "error" in result

    def test_get_event_errors_returns_list(self):
        runner = PowerShellRunner()
        result = runner.get_event_errors(hours=24)
        assert isinstance(result, list)

    def test_get_installed_software_returns_list(self):
        runner = PowerShellRunner()
        result = runner.get_installed_software()
        assert isinstance(result, list)

    def test_get_disk_usage_returns_list(self):
        runner = PowerShellRunner()
        result = runner.get_disk_usage()
        assert isinstance(result, list)

    def test_get_network_config_returns_list(self):
        runner = PowerShellRunner()
        result = runner.get_network_config()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# get_default_runner
# ---------------------------------------------------------------------------

class TestGetDefaultRunner:
    @patch.dict("sys.modules", {"core.powershell": __import__("core.powershell", fromlist=["_default_runner"])})
    def test_returns_runner_instance(self):
        # Reset the global
        import core.powershell as ps
        ps._default_runner = None
        runner = get_default_runner()
        assert isinstance(runner, PowerShellRunner)

    def test_returns_same_instance(self):
        import core.powershell as ps
        ps._default_runner = None
        a = get_default_runner()
        b = get_default_runner()
        assert a is b


# ---------------------------------------------------------------------------
# _resolve_ps_exe
# ---------------------------------------------------------------------------

class TestResolvePsExe:
    @patch("core.powershell._is_windows", return_value=False)
    def test_non_windows_returns_powershell_exe(self, mock_win):
        runner = PowerShellRunner()
        assert runner._ps_exe == "powershell.exe"

    @patch("core.powershell._is_windows", return_value=True)
    @patch("shutil.which", return_value=None)
    def test_windows_no_where_falls_back(self, mock_which, mock_win):
        runner = PowerShellRunner()
        assert runner._ps_exe == "powershell.exe"

    @patch("core.powershell._is_windows", return_value=True)
    @patch("shutil.which", return_value="C:\\Program Files\\pwsh.exe")
    def test_windows_finds_pwsh(self, mock_which, mock_win):
        runner = PowerShellRunner()
        assert runner._ps_exe == "pwsh.exe"
