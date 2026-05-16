"""Tests for core/system_info.py — system information gathering."""

import sys
from unittest.mock import MagicMock, patch

from core.system_info import _screen_resolution, brief_system_info, system_info


class TestBriefSystemInfo:
    @patch("core.system_info._screen_resolution", return_value="1920x1080")
    @patch("core.system_info.psutil")
    def test_returns_formatted_string(self, mock_psutil, mock_screen):
        mock_mem = MagicMock()
        mock_mem.used = 8 * 1024**3
        mock_mem.total = 16 * 1024**3
        mock_mem.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_mem
        mock_psutil.cpu_percent.return_value = 25.0
        mock_psutil.cpu_count.return_value = 8

        result = brief_system_info()
        assert "OS:" in result
        assert "Hostname:" in result
        assert "CPU:" in result
        assert "RAM:" in result
        assert "Screen: 1920x1080" in result
        assert "25.0% used" in result
        assert "8 cores" in result

    @patch("core.system_info._screen_resolution", return_value="unknown")
    @patch("core.system_info.psutil")
    def test_handles_unknown_screen(self, mock_psutil, mock_screen):
        mock_mem = MagicMock()
        mock_mem.used = 4 * 1024**3
        mock_mem.total = 8 * 1024**3
        mock_mem.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_mem
        mock_psutil.cpu_percent.return_value = 10.0
        mock_psutil.cpu_count.return_value = 4

        result = brief_system_info()
        assert "Screen: unknown" in result


class TestSystemInfo:
    @patch("core.system_info._screen_resolution", return_value="2560x1440")
    @patch("core.system_info.psutil")
    def test_returns_dict_with_expected_keys(self, mock_psutil, mock_screen):
        mock_mem = MagicMock()
        mock_mem.total = 32 * 1024**3
        mock_mem.used = 16 * 1024**3
        mock_mem.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_mem
        mock_psutil.cpu_percent.return_value = 30.0
        mock_psutil.cpu_count.return_value = 12
        mock_disk = MagicMock()
        mock_disk.total = 500 * 1024**3
        mock_disk.used = 250 * 1024**3
        mock_disk.percent = 50.0
        mock_psutil.disk_usage.return_value = mock_disk

        result = system_info()
        expected_keys = {
            "os",
            "hostname",
            "arch",
            "cpu_percent",
            "cpu_count",
            "memory_total_gb",
            "memory_used_gb",
            "memory_percent",
            "disk_total_gb",
            "disk_used_gb",
            "disk_percent",
            "screen_resolution",
        }
        assert set(result.keys()) == expected_keys
        assert result["cpu_count"] == 12
        assert result["memory_total_gb"] == 32.0
        assert result["screen_resolution"] == "2560x1440"

    @patch("core.system_info._screen_resolution", return_value="1920x1080")
    @patch("core.system_info.psutil")
    def test_disk_failure_uses_zero_fallback(self, mock_psutil, mock_screen):
        mock_mem = MagicMock()
        mock_mem.total = 16 * 1024**3
        mock_mem.used = 8 * 1024**3
        mock_mem.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_mem
        mock_psutil.cpu_percent.return_value = 10.0
        mock_psutil.cpu_count.return_value = 4
        mock_psutil.disk_usage.side_effect = PermissionError("no access")

        result = system_info()
        assert result["disk_total_gb"] == 0
        assert result["disk_used_gb"] == 0
        assert result["disk_percent"] == 0.0


class TestScreenResolution:
    def test_returns_resolution_string(self):
        mock_pyauto = MagicMock()
        mock_pyauto.size.return_value = (1920, 1080)
        with patch.dict("sys.modules", {"pyautogui": mock_pyauto}):
            result = _screen_resolution()
            assert result == "1920x1080"

    def test_import_error_returns_unknown(self):
        # Block pyautogui import to trigger the except branch
        import builtins

        real_import = builtins.__import__

        def blocking_import(name, *args, **kwargs):
            if name == "pyautogui":
                raise ImportError("blocked for test")
            return real_import(name, *args, **kwargs)

        saved = sys.modules.pop("pyautogui", None)
        try:
            with patch("builtins.__import__", side_effect=blocking_import):
                result = _screen_resolution()
                assert result == "unknown"
        finally:
            if saved is not None:
                sys.modules["pyautogui"] = saved

    def test_generic_exception_returns_unknown(self):
        """Any exception (not just ImportError) returns 'unknown'."""
        mock_pyauto = MagicMock()
        mock_pyauto.size.side_effect = RuntimeError("display driver crashed")
        with patch.dict("sys.modules", {"pyautogui": mock_pyauto}):
            result = _screen_resolution()
            assert result == "unknown"

    def test_callable(self):
        assert callable(_screen_resolution)


class TestBriefSystemInfoPsutilFailure:
    @patch("core.system_info._screen_resolution", return_value="1920x1080")
    @patch("core.system_info.psutil")
    def test_psutil_virtual_memory_raises(self, mock_psutil, mock_screen):
        """brief_system_info handles psutil failure gracefully."""
        mock_psutil.virtual_memory.side_effect = RuntimeError("snmp blocked")
        mock_psutil.cpu_percent.return_value = 0.0
        mock_psutil.cpu_count.return_value = 0

        result = brief_system_info()
        assert "RAM: unavailable" in result
        assert "CPU: 0.0% used, 0 cores" in result


class TestBriefSystemInfoSocketFailure:
    """Cover lines 30-31: socket.gethostname() OSError in brief_system_info."""

    @patch("core.system_info._screen_resolution", return_value="1920x1080")
    @patch("core.system_info.psutil")
    @patch("core.system_info.socket.gethostname", side_effect=OSError("no network"))
    def test_hostname_falls_back_to_unknown(self, mock_socket, mock_psutil, mock_screen):
        mock_mem = MagicMock()
        mock_mem.used = 4 * 1024**3
        mock_mem.total = 8 * 1024**3
        mock_mem.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_mem
        mock_psutil.cpu_percent.return_value = 10.0
        mock_psutil.cpu_count.return_value = 4

        result = brief_system_info()
        assert "Hostname: unknown" in result
        # Confirm the rest of the output is still populated correctly
        assert "CPU:" in result
        assert "RAM:" in result


class TestBriefSystemInfoPsutilAndSocketFailure:
    """Cover both psutil and socket failures in brief_system_info."""

    @patch("core.system_info._screen_resolution", return_value="unknown")
    @patch("core.system_info.psutil")
    @patch("core.system_info.socket.gethostname", side_effect=OSError("DNS fail"))
    def test_psutil_and_socket_both_fail(self, mock_socket, mock_psutil, mock_screen):
        mock_psutil.virtual_memory.side_effect = RuntimeError("access denied")
        mock_psutil.cpu_percent.return_value = 0.0
        mock_psutil.cpu_count.return_value = 0

        result = brief_system_info()
        assert "RAM: unavailable" in result
        assert "Hostname: unknown" in result
        assert "CPU: 0.0% used, 0 cores" in result
        assert "Screen: unknown" in result


class TestSystemInfoMemoryFailure:
    """Cover lines 48-52: psutil.virtual_memory() failure in system_info."""

    @patch("core.system_info._screen_resolution", return_value="1920x1080")
    @patch("core.system_info.psutil")
    def test_memory_failure_returns_zeroes(self, mock_psutil, mock_screen):
        mock_psutil.virtual_memory.side_effect = RuntimeError("driver error")
        mock_psutil.cpu_percent.return_value = 15.0
        mock_psutil.cpu_count.return_value = 6
        mock_disk = MagicMock()
        mock_disk.total = 200 * 1024**3
        mock_disk.used = 100 * 1024**3
        mock_disk.percent = 50.0
        mock_psutil.disk_usage.return_value = mock_disk

        result = system_info()
        assert result["memory_total_gb"] == 0.0
        assert result["memory_used_gb"] == 0.0
        assert result["memory_percent"] == 0.0
        # Other fields should still be populated
        assert result["cpu_percent"] == 15.0
        assert result["cpu_count"] == 6
        assert result["disk_total_gb"] == 200.0

    @patch("core.system_info._screen_resolution", return_value="1920x1080")
    @patch("core.system_info.psutil")
    def test_memory_oserror_returns_zeroes(self, mock_psutil, mock_screen):
        mock_psutil.virtual_memory.side_effect = OSError("permission denied")
        mock_psutil.cpu_percent.return_value = 5.0
        mock_psutil.cpu_count.return_value = 2
        mock_disk = MagicMock()
        mock_disk.total = 100 * 1024**3
        mock_disk.used = 50 * 1024**3
        mock_disk.percent = 50.0
        mock_psutil.disk_usage.return_value = mock_disk

        result = system_info()
        assert result["memory_total_gb"] == 0.0
        assert result["memory_used_gb"] == 0.0
        assert result["memory_percent"] == 0.0


class TestSystemInfoCpuFailure:
    """Cover lines 57-60: psutil cpu_percent/cpu_count failure in system_info."""

    @patch("core.system_info._screen_resolution", return_value="1920x1080")
    @patch("core.system_info.psutil")
    def test_cpu_failure_returns_zeroes(self, mock_psutil, mock_screen):
        mock_mem = MagicMock()
        mock_mem.total = 16 * 1024**3
        mock_mem.used = 8 * 1024**3
        mock_mem.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_mem
        mock_psutil.cpu_percent.side_effect = RuntimeError("kernel error")
        mock_disk = MagicMock()
        mock_disk.total = 300 * 1024**3
        mock_disk.used = 150 * 1024**3
        mock_disk.percent = 50.0
        mock_psutil.disk_usage.return_value = mock_disk

        result = system_info()
        assert result["cpu_percent"] == 0.0
        assert result["cpu_count"] == 0
        # Memory and disk should still work
        assert result["memory_total_gb"] == 16.0
        assert result["disk_total_gb"] == 300.0

    @patch("core.system_info._screen_resolution", return_value="1920x1080")
    @patch("core.system_info.psutil")
    def test_cpu_oserror_returns_zeroes(self, mock_psutil, mock_screen):
        mock_mem = MagicMock()
        mock_mem.total = 8 * 1024**3
        mock_mem.used = 4 * 1024**3
        mock_mem.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_mem
        mock_psutil.cpu_percent.side_effect = OSError("syscall failed")
        mock_disk = MagicMock()
        mock_disk.total = 100 * 1024**3
        mock_disk.used = 50 * 1024**3
        mock_disk.percent = 50.0
        mock_psutil.disk_usage.return_value = mock_disk

        result = system_info()
        assert result["cpu_percent"] == 0.0
        assert result["cpu_count"] == 0


class TestSystemInfoSocketFailure:
    """Cover lines 64-66: socket.gethostname() failure in system_info."""

    @patch("core.system_info._screen_resolution", return_value="1920x1080")
    @patch("core.system_info.psutil")
    @patch("core.system_info.socket.gethostname", side_effect=OSError("unreachable"))
    def test_hostname_falls_back_to_unknown(self, mock_socket, mock_psutil, mock_screen):
        mock_mem = MagicMock()
        mock_mem.total = 16 * 1024**3
        mock_mem.used = 8 * 1024**3
        mock_mem.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_mem
        mock_psutil.cpu_percent.return_value = 10.0
        mock_psutil.cpu_count.return_value = 4
        mock_disk = MagicMock()
        mock_disk.total = 200 * 1024**3
        mock_disk.used = 100 * 1024**3
        mock_disk.percent = 50.0
        mock_psutil.disk_usage.return_value = mock_disk

        result = system_info()
        assert result["hostname"] == "unknown"
        # Everything else should still be populated
        assert result["memory_total_gb"] == 16.0
        assert result["cpu_count"] == 4
        assert result["disk_total_gb"] == 200.0


class TestSystemInfoAllFailures:
    """Cover combined failure of memory, cpu, socket, and disk in system_info."""

    @patch("core.system_info._screen_resolution", return_value="unknown")
    @patch("core.system_info.psutil")
    @patch("core.system_info.socket.gethostname", side_effect=OSError("no network"))
    def test_everything_fails_gracefully(self, mock_socket, mock_psutil, mock_screen):
        mock_psutil.virtual_memory.side_effect = RuntimeError("unavailable")
        mock_psutil.cpu_percent.side_effect = OSError("denied")
        mock_psutil.disk_usage.side_effect = PermissionError("no access")

        result = system_info()
        assert result["memory_total_gb"] == 0.0
        assert result["memory_used_gb"] == 0.0
        assert result["memory_percent"] == 0.0
        assert result["cpu_percent"] == 0.0
        assert result["cpu_count"] == 0
        assert result["hostname"] == "unknown"
        assert result["disk_total_gb"] == 0
        assert result["disk_used_gb"] == 0
        assert result["disk_percent"] == 0.0
        assert result["screen_resolution"] == "unknown"
        # os and arch should still be present (platform calls don't fail)
        assert "os" in result
        assert "arch" in result


class TestSystemInfoNonWindows:
    @patch("core.system_info.platform.system", return_value="Linux")
    @patch("core.system_info._screen_resolution", return_value="1920x1080")
    @patch("core.system_info.psutil")
    def test_uses_slash_root_on_linux(self, mock_psutil, mock_screen, mock_platform):
        """system_info uses '/' disk path on non-Windows."""
        mock_mem = MagicMock()
        mock_mem.total = 16 * 1024**3
        mock_mem.used = 8 * 1024**3
        mock_mem.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_mem
        mock_psutil.cpu_percent.return_value = 10.0
        mock_psutil.cpu_count.return_value = 4
        mock_disk = MagicMock()
        mock_disk.total = 200 * 1024**3
        mock_disk.used = 100 * 1024**3
        mock_disk.percent = 50.0
        mock_psutil.disk_usage.return_value = mock_disk

        result = system_info()
        mock_psutil.disk_usage.assert_called_once_with("/")
        assert result["disk_total_gb"] == 200.0
