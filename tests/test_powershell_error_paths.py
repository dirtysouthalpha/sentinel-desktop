"""Gap-coverage tests for core/powershell.py uncovered error paths.

Exercises lines 243-244, 257-277, 389, 423, 479.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.powershell import PowerShellRunner, PSResult

# ---------------------------------------------------------------------------
# _run() exception paths (lines 257-277) — need to mock _is_windows
# ---------------------------------------------------------------------------


class TestRunExceptions:
    """Test _run() exception handling paths."""

    def _make_runner(self, **kwargs):
        return PowerShellRunner(timeout=10, **kwargs)

    def test_run_timeout_expired(self):
        """_run returns PSResult with exit_code=-2 on TimeoutExpired."""
        runner = self._make_runner()
        with patch("core.powershell._is_windows", return_value=True), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ps", 10)):
            result = runner._run("Get-Date")

        assert result.success is False
        assert result.exit_code == -2
        assert "timed out" in result.stderr

    def test_run_file_not_found(self):
        """_run returns PSResult with exit_code=-3 on FileNotFoundError."""
        runner = self._make_runner()
        with patch("core.powershell._is_windows", return_value=True), \
             patch("subprocess.run", side_effect=FileNotFoundError("no pwsh")):
            result = runner._run("Get-Date")

        assert result.success is False
        assert result.exit_code == -3
        assert "not found" in result.stderr

    def test_run_os_error(self):
        """_run returns PSResult with exit_code=-4 on OSError."""
        runner = self._make_runner()
        with patch("core.powershell._is_windows", return_value=True), \
             patch("subprocess.run", side_effect=OSError("broken")):
            result = runner._run("Get-Date")

        assert result.success is False
        assert result.exit_code == -4
        assert "broken" in result.stderr

    def test_run_subprocess_error(self):
        """_run returns PSResult with exit_code=-4 on SubprocessError."""
        runner = self._make_runner()
        with patch("core.powershell._is_windows", return_value=True), \
             patch("subprocess.run", side_effect=subprocess.SubprocessError("sub error")):
            result = runner._run("Get-Date")

        assert result.success is False
        assert result.exit_code == -4
        assert "sub error" in result.stderr

    def test_run_runtime_error(self):
        """_run returns PSResult with exit_code=-4 on RuntimeError."""
        runner = self._make_runner()
        with patch("core.powershell._is_windows", return_value=True), \
             patch("subprocess.run", side_effect=RuntimeError("oops")):
            result = runner._run("Get-Date")

        assert result.success is False
        assert result.exit_code == -4
        assert "oops" in result.stderr


# ---------------------------------------------------------------------------
# _run() elevated output read failure (lines 243-244)
# ---------------------------------------------------------------------------


class TestRunElevatedOutputReadFailure:
    """Test _run handles OSError reading elevated output temp file."""

    def test_elevated_output_read_oserror(self, tmp_path):
        """_run handles OSError when reading the elevated output temp file."""
        runner = PowerShellRunner(timeout=10, run_as_admin=True)

        # Create a mock CompletedProcess
        mock_cp = MagicMock()
        mock_cp.returncode = 0
        mock_cp.stdout = ""
        mock_cp.stderr = ""

        # The command needs to contain a .tmp filename for the code to find it
        tmp_file = tmp_path / "test_output.tmp"
        tmp_file.write_text("data")
        cmd_with_tmp = f"Get-Process | Out-File {tmp_file}"

        original_is_file = Path.is_file

        def mock_is_file(self_path):
            # Return True for our temp file, real behavior for others
            if str(self_path).endswith("test_output.tmp"):
                return True
            return original_is_file(self_path)

        original_open = Path.open

        def mock_open(self_path, *args, **kwargs):
            if str(self_path).endswith("test_output.tmp"):
                raise OSError("permission denied")
            return original_open(self_path, *args, **kwargs)

        with patch("core.powershell._is_windows", return_value=True), \
             patch("subprocess.run", return_value=mock_cp), \
             patch.object(Path, "is_file", mock_is_file), \
             patch.object(Path, "open", mock_open), \
             patch.object(Path, "unlink"):
            result = runner._run(cmd_with_tmp)

        # Should still return a result, with empty stdout since read failed
        assert isinstance(result, PSResult)


# ---------------------------------------------------------------------------
# get_service_status objects[0] path (line 389)
# ---------------------------------------------------------------------------


class TestGetServiceStatusObjectsPath:
    """Test get_service_status returns first object when available."""

    def test_returns_first_object_on_success(self):
        """get_service_status returns objects[0] when result has objects."""
        runner = PowerShellRunner(timeout=10)
        expected = {"Name": "wuauserv", "Status": "Running", "StartType": "Manual", "DisplayName": "Windows Update"}

        with patch.object(runner, "_run") as mock_run:
            mock_run.return_value = PSResult(
                success=True,
                exit_code=0,
                stdout="",
                stderr="",
                objects=[expected],
            )
            result = runner.get_service_status("wuauserv")

        assert result["Name"] == "wuauserv"
        assert result["Status"] == "Running"

    def test_returns_error_dict_on_failure(self):
        """get_service_status returns error dict when result fails."""
        runner = PowerShellRunner(timeout=10)

        with patch.object(runner, "_run") as mock_run:
            mock_run.return_value = PSResult(
                success=False,
                exit_code=1,
                stdout="",
                stderr="service not found",
                objects=[],
            )
            result = runner.get_service_status("nonexistent")

        assert result["Status"] == "Unknown"
        assert "error" in result

    def test_returns_error_dict_on_success_no_objects(self):
        """get_service_status returns error dict when success but no objects."""
        runner = PowerShellRunner(timeout=10)

        with patch.object(runner, "_run") as mock_run:
            mock_run.return_value = PSResult(
                success=True,
                exit_code=0,
                stdout="",
                stderr="",
                objects=[],
            )
            result = runner.get_service_status("someservice")

        assert result["Status"] == "Unknown"


# ---------------------------------------------------------------------------
# restart_service objects[0] path (line 423)
# ---------------------------------------------------------------------------


class TestRestartServiceObjectsPath:
    """Test restart_service returns first object when available."""

    def test_returns_first_object_on_success(self):
        """restart_service returns objects[0] when result has objects."""
        runner = PowerShellRunner(timeout=10)
        expected = {"Name": "spooler", "Status": "Running", "Action": "Restart", "Success": True}

        with patch.object(runner, "_run") as mock_run:
            mock_run.return_value = PSResult(
                success=True,
                exit_code=0,
                stdout="",
                stderr="",
                objects=[expected],
            )
            result = runner.restart_service("spooler")

        assert result["Name"] == "spooler"
        assert result["Success"] is True

    def test_returns_error_dict_on_failure(self):
        """restart_service returns error dict when result fails."""
        runner = PowerShellRunner(timeout=10)

        with patch.object(runner, "_run") as mock_run:
            mock_run.return_value = PSResult(
                success=False,
                exit_code=1,
                stdout="",
                stderr="access denied",
                objects=[],
            )
            result = runner.restart_service("nonexistent")

        assert result["Status"] == "Error"


# ---------------------------------------------------------------------------
# test_connection objects[0] path (line 479)
# ---------------------------------------------------------------------------


class TestTestConnectionObjectsPath:
    """Test test_connection returns first object when available."""

    def test_returns_first_object_on_success(self):
        """test_connection returns objects[0] when result has objects."""
        runner = PowerShellRunner(timeout=10)
        expected = {"Host": "google.com", "PingSucceeded": True, "PingMs": 12.5}

        with patch.object(runner, "_run") as mock_run:
            mock_run.return_value = PSResult(
                success=True,
                exit_code=0,
                stdout="",
                stderr="",
                objects=[expected],
            )
            result = runner.test_connection("google.com")

        assert result["Host"] == "google.com"
        assert result["PingSucceeded"] is True
        assert result["PingMs"] == 12.5

    def test_returns_failure_dict_on_no_objects(self):
        """test_connection returns failure dict when result has no objects."""
        runner = PowerShellRunner(timeout=10)

        with patch.object(runner, "_run") as mock_run:
            mock_run.return_value = PSResult(
                success=False,
                exit_code=1,
                stdout="",
                stderr="timeout",
                objects=[],
            )
            result = runner.test_connection("unreachable.local")

        assert result["PingSucceeded"] is False
        assert result["PingMs"] == 0
