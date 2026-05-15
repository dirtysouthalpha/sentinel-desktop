"""Tests for core/powershell.py — argument escaping, PSResult, JSON parsing."""

from core.powershell import (
    PSResult,
    PowerShellRunner,
    _ps_escape_single_quoted,
)


class TestPsEscapeSingleQuoted:
    def test_simple_string(self):
        assert _ps_escape_single_quoted("hello") == "'hello'"

    def test_embedded_single_quote(self):
        assert _ps_escape_single_quoted("it's") == "'it''s'"

    def test_multiple_quotes(self):
        assert _ps_escape_single_quoted("a'b'c") == "'a''b''c'"

    def test_empty_string(self):
        assert _ps_escape_single_quoted("") == "''"

    def test_rejects_null_byte(self):
        try:
            _ps_escape_single_quoted("hello\x00world")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_rejects_carriage_return(self):
        try:
            _ps_escape_single_quoted("hello\rworld")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_rejects_newline(self):
        try:
            _ps_escape_single_quoted("hello\nworld")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_rejects_non_string(self):
        try:
            _ps_escape_single_quoted(42)
            assert False, "Should have raised TypeError"
        except TypeError:
            pass


class TestPSResult:
    def test_str_success(self):
        r = PSResult(success=True, exit_code=0, stdout="hello", stderr="", objects=[{"a": 1}])
        s = str(r)
        assert "OK" in s
        assert "code=0" in s
        assert "5c" in s
        assert "objects=1" in s

    def test_str_failure(self):
        r = PSResult(success=False, exit_code=1, stdout="", stderr="error", objects=[])
        s = str(r)
        assert "FAIL" in s
        assert "code=1" in s


class TestParseJsonOutput:
    def test_empty_string(self):
        assert PowerShellRunner._parse_json_output("") == []

    def test_whitespace_only(self):
        assert PowerShellRunner._parse_json_output("   ") == []

    def test_json_object(self):
        result = PowerShellRunner._parse_json_output('{"Name": "test"}')
        assert result == [{"Name": "test"}]

    def test_json_array(self):
        result = PowerShellRunner._parse_json_output('[{"a": 1}, {"b": 2}]')
        assert len(result) == 2

    def test_json_scalar(self):
        result = PowerShellRunner._parse_json_output('42')
        assert result == [{"value": 42}]

    def test_invalid_json(self):
        assert PowerShellRunner._parse_json_output("not json") == []


class TestPowerShellRunnerAllowRaw:
    def test_run_command_refused(self):
        runner = PowerShellRunner(allow_raw=False)
        result = runner.run_command("Get-Process")
        assert result.success is False
        assert "allow_raw=False" in result.stderr
        assert result.exit_code == -5

    def test_run_inline_refused(self):
        runner = PowerShellRunner(allow_raw=False)
        result = runner.run_inline("Get-Process | Select -First 1")
        assert result.success is False
        assert "allow_raw=False" in result.stderr
        assert result.exit_code == -5

    def test_run_script_not_found(self):
        runner = PowerShellRunner()
        result = runner.run_script("/nonexistent/script.ps1")
        assert result.success is False
        assert "not found" in result.stderr.lower()

    def test_get_service_status_rejects_bad_name(self):
        runner = PowerShellRunner()
        result = runner.get_service_status("bad\x00name")
        assert result["Status"] == "Unknown"
        assert "error" in result

    def test_test_connection_rejects_bad_host(self):
        runner = PowerShellRunner()
        result = runner.test_connection("bad\x00host")
        assert result["PingSucceeded"] is False
        assert "error" in result

    def test_restart_service_rejects_bad_name(self):
        runner = PowerShellRunner()
        result = runner.restart_service("bad\x00name")
        assert result["Success"] is False
        assert "error" in result
