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

    def test_callable(self):
        assert callable(_screen_resolution)
