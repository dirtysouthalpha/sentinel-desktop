"""Gap tests for net_tools.py — Windows-specific import guards (lines 156, 251).

The module has Windows-specific branches that use different command-line arguments:
- Line 156: ping command uses Windows-style args (-n, -w) vs Unix-style (-c, -W)
- Line 251: traceroute uses "tracert" on Windows vs "traceroute" on Unix

These lines execute at runtime when _IS_WINDOWS is True, but they are never
reached on Linux during normal testing. We use importlib.reload() with mocked
conditions to execute these branches and verify they work correctly.
"""

import importlib
from unittest.mock import MagicMock, patch

import pytest

import core.net_tools as net_tools_mod


class TestWindowsPingCommand:
    """Line 156: Windows ping command uses different arguments."""

    def test_windows_ping_uses_windows_args(self):
        """When _IS_WINDOWS is True, ping uses Windows-style arguments."""
        with patch.object(net_tools_mod, "_IS_WINDOWS", True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="Reply from 142.250.80.46: bytes=32 time=12ms TTL=118\n",
                    stderr=""
                )

                net_tools_mod.ping_host("example.com", count=4, timeout=2)

                # Verify Windows-style ping arguments were used
                args, kwargs = mock_run.call_args
                cmd = args[0]
                assert cmd[0] == "ping"
                assert "-n" in cmd  # Windows count flag
                assert "-w" in cmd  # Windows timeout flag (milliseconds)
                assert "4" in cmd  # count value
                assert cmd[cmd.index("-w") + 1] == "2000"  # timeout in ms

    def test_unix_ping_uses_unix_args(self):
        """When _IS_WINDOWS is False, ping uses Unix-style arguments."""
        with patch.object(net_tools_mod, "_IS_WINDOWS", False):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="64 bytes from 142.250.80.46: icmp_seq=1 ttl=118 time=12.3 ms\n",
                    stderr=""
                )

                net_tools_mod.ping_host("example.com", count=4, timeout=2)

                # Verify Unix-style ping arguments were used
                args, kwargs = mock_run.call_args
                cmd = args[0]
                assert cmd[0] == "ping"
                assert "-c" in cmd  # Unix count flag
                assert "-W" in cmd  # Unix timeout flag (seconds)
                assert "4" in cmd  # count value
                assert cmd[cmd.index("-W") + 1] == "2"  # timeout in seconds
                assert "--" in cmd  # Safety separator


class TestWindowsTracerouteCommand:
    """Line 251: Windows traceroute uses different command and arguments."""

    def test_windows_traceroute_uses_tracert(self):
        """When _IS_WINDOWS is True, traceroute uses tracert with Windows args."""
        with patch.object(net_tools_mod, "_IS_WINDOWS", True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="Tracing route to example.com [93.184.216.34]\n",
                    stderr=""
                )

                net_tools_mod.traceroute("example.com", max_hops=30)

                # Verify Windows traceroute command was used
                args, kwargs = mock_run.call_args
                cmd = args[0]
                assert cmd[0] == "tracert"
                assert "-d" in cmd  # Don't resolve addresses
                assert "-h" in cmd  # Max hops
                assert "30" in cmd  # max_hops value

    def test_unix_traceroute_uses_traceroute(self):
        """When _IS_WINDOWS is False, traceroute uses Unix traceroute."""
        with patch.object(net_tools_mod, "_IS_WINDOWS", False):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="traceroute to example.com (93.184.216.34), 30 hops max\n",
                    stderr=""
                )

                net_tools_mod.traceroute("example.com", max_hops=30)

                # Verify Unix traceroute command was used
                args, kwargs = mock_run.call_args
                cmd = args[0]
                assert cmd[0] == "traceroute"
                assert "-n" in cmd  # Don't resolve addresses
                assert "-m" in cmd  # Max hops
                assert "30" in cmd  # max_hops value
                assert "--" in cmd  # Safety separator


class TestModuleLevelPlatformDetection:
    """Line 28: Module-level _IS_WINDOWS platform detection."""

    def test_module_level_platform_detection(self):
        """Verify _IS_WINDOWS is set correctly at module level."""
        import platform as _plat

        # The module should have _IS_WINDOWS set correctly based on actual platform
        expected_is_windows = _plat.system() == "Windows"
        assert net_tools_mod._IS_WINDOWS is expected_is_windows

    def test_reload_with_mocked_platform_windows(self):
        """When reloaded with Windows platform, _IS_WINDOWS becomes True."""
        import sys
        original_platform = sys.platform

        try:
            # Patch sys.platform to simulate Windows
            sys.platform = "win32"
            reloaded = importlib.reload(net_tools_mod)
            # After reload on Windows, _IS_WINDOWS should be True
            assert reloaded._IS_WINDOWS is True
        finally:
            # Restore the actual platform
            sys.platform = original_platform
            importlib.reload(net_tools_mod)

        # Verify we're back to the real platform state
        expected_is_windows = sys.platform == "win32"
        assert net_tools_mod._IS_WINDOWS is expected_is_windows

    def test_reload_with_mocked_platform_linux(self):
        """When reloaded with Linux platform, _IS_WINDOWS becomes False."""
        import sys
        original_platform = sys.platform

        try:
            # Patch sys.platform to simulate Linux
            sys.platform = "linux"
            reloaded = importlib.reload(net_tools_mod)
            # After reload on Linux, _IS_WINDOWS should be False
            assert reloaded._IS_WINDOWS is False
        finally:
            # Restore the actual platform
            sys.platform = original_platform
            importlib.reload(net_tools_mod)

        # Verify we're back to the real platform state
        expected_is_windows = sys.platform == "win32"
        assert net_tools_mod._IS_WINDOWS is expected_is_windows
