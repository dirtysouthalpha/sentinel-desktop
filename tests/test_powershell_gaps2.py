"""Gap tests for powershell.py — elevated _run path, run_script with args, run_command allow_raw."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.powershell import PowerShellRunner


def _make_runner(**overrides):
    runner = PowerShellRunner.__new__(PowerShellRunner)
    runner._ps_exe = "powershell.exe"
    runner.timeout = 30
    runner.working_dir = "."
    runner.run_as_admin = False
    runner.env_vars = {}
    runner.allow_raw = True
    for k, v in overrides.items():
        setattr(runner, k, v)
    return runner


class TestRunElevatedPath:
    """_run with run_as_admin=True exercises elevated command wrapping (lines 190-198)."""

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_elevated_builds_start_process_command(self, mock_run, mock_iw):
        mock_proc = MagicMock(returncode=0, stdout="", stderr="")
        mock_run.return_value = mock_proc
        runner = _make_runner(run_as_admin=True)
        result = runner._run("Get-Date")
        assert result.success is True
        args_passed = mock_run.call_args[0][0]
        cmd_str = " ".join(args_passed)
        assert "Start-Process" in cmd_str
        assert "RunAs" in cmd_str

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_elevated_reads_tmp_output_file(self, mock_run, mock_iw, tmp_path):
        tmp_out = tmp_path / "elevated_output.tmp"
        tmp_out.write_text('{"Result": "ok"}', encoding="utf-8")
        tmp_name = str(tmp_out)
        mock_proc = MagicMock(returncode=0, stdout="", stderr="")
        mock_run.return_value = mock_proc
        runner = _make_runner(run_as_admin=True)
        # The elevated path splits command by space and looks for .tmp suffix
        result = runner._run(f"Get-Date {tmp_name}")
        assert result.success is True
        assert not tmp_out.exists()  # temp file should be cleaned up

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_elevated_tmp_read_failure(self, mock_run, mock_iw, tmp_path):
        tmp_out = tmp_path / "missing.tmp"
        tmp_name = str(tmp_out)
        mock_proc = MagicMock(returncode=0, stdout="", stderr="")
        mock_run.return_value = mock_proc
        runner = _make_runner(run_as_admin=True)
        result = runner._run(f"Get-Date {tmp_name}")
        assert result.success is True
        assert result.stdout == ""

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_elevated_tmp_unlink_failure(self, mock_run, mock_iw, tmp_path):
        tmp_out = tmp_path / "readonly.tmp"
        tmp_out.write_text('{"X": 1}', encoding="utf-8")
        tmp_name = str(tmp_out)
        mock_proc = MagicMock(returncode=0, stdout="", stderr="")
        mock_run.return_value = mock_proc
        runner = _make_runner(run_as_admin=True)
        result = runner._run(f"Get-Date {tmp_name}")
        assert result.success is True


class TestRunScriptWithArgs:
    """run_script with arguments builds proper parameter string (lines 284-288)."""

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_run_script_with_args(self, mock_run, mock_iw, tmp_path):
        script = tmp_path / "test.ps1"
        script.write_text("Write-Host 'hi'", encoding="utf-8")
        mock_proc = MagicMock(returncode=0, stdout='"hello"', stderr="")
        mock_run.return_value = mock_proc
        runner = _make_runner()
        result = runner.run_script(str(script), args={"Name": "World", "Count": 3})
        assert result.success is True
        args_passed = mock_run.call_args[0][0]
        cmd_str = " ".join(args_passed)
        assert "-Name" in cmd_str
        assert "-Count" in cmd_str

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_run_script_no_args(self, mock_run, mock_iw, tmp_path):
        script = tmp_path / "test.ps1"
        script.write_text("Write-Host 'hi'", encoding="utf-8")
        mock_proc = MagicMock(returncode=0, stdout='"ok"', stderr="")
        mock_run.return_value = mock_proc
        runner = _make_runner()
        result = runner.run_script(str(script))
        assert result.success is True


class TestRunCommandAllowRawTrue:
    """run_command with allow_raw=True delegates to _run (line 305)."""

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_allow_raw_true_executes(self, mock_run, mock_iw):
        mock_proc = MagicMock(returncode=0, stdout='"2025-01-01"', stderr="")
        mock_run.return_value = mock_proc
        runner = _make_runner(allow_raw=True)
        result = runner.run_command("Get-Date")
        assert result.success is True


class TestResolvePs_ExeBothFail:
    """_resolve_ps_exe falls through all candidates and returns default (line 154 False branch)."""

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_all_candidates_nonzero_returncode(self, mock_run, mock_iw):
        # Both candidates return non-zero exit code → the if on line 154 is False each time
        mock_proc = MagicMock(returncode=1, stdout="", stderr="")
        mock_run.return_value = mock_proc
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner._resolve_ps_exe()
        assert result == PowerShellRunner.POWERSHELL_EXE

    @patch("core.powershell._is_windows", return_value=True)
    @patch("core.powershell.subprocess.run")
    def test_all_candidates_empty_stdout(self, mock_run, mock_iw):
        # returncode=0 but stdout is empty → stdout.strip() is falsy → if is False
        mock_proc = MagicMock(returncode=0, stdout="", stderr="")
        mock_run.return_value = mock_proc
        runner = PowerShellRunner.__new__(PowerShellRunner)
        result = runner._resolve_ps_exe()
        assert result == PowerShellRunner.POWERSHELL_EXE
