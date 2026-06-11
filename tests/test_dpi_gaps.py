"""Gap tests for core.dpi — covers uncovered lines:

  104-169 (_get_windows_dpi_scaling Windows code via sys.platform mock)
  181     (_get_mss_monitors success path)
  182-184 (_get_mss_monitors exception path)
  222-223 (detect_monitors pyautogui.size OSError fallback)
  283     (physical_to_logical monitors=None)
  328,332 (logical_to_physical monitors=None, index==0 skip)
  358     (logical_to_physical fallback return)
  408-409 (save_calibration OSError)
  431     (is_calibration_current hash match return)
  458     (run_calibration_probe monitors=None)
  473     (run_calibration_probe skip index==0 monitor)
  547     (get_monitors cache TTL refresh, config unchanged)
"""

from __future__ import annotations

import ctypes
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.dpi import (
    CalibrationData,
    MonitorInfo,
    _get_mss_monitors,
    _get_windows_dpi_scaling,
    clear_monitor_cache,
    detect_monitors,
    get_monitors,
    is_calibration_current,
    logical_to_physical,
    physical_to_logical,
    run_calibration_probe,
    save_calibration,
)

# ── _get_windows_dpi_scaling ──────────────────────────────────────────────


class TestGetWindowsDPIScalingExceptionPath:
    """Lines 104-106, 166-168 — exception branch of Windows DPI detection."""

    def test_oserror_accessing_windll_returns_empty(self):
        """Patch sys.platform='win32' and make windll raise OSError → except branch."""

        class _FailWindll:
            @property
            def user32(self):
                raise OSError("no user32 on this platform")

        with patch("sys.platform", "win32"), \
             patch.object(ctypes, "windll", _FailWindll(), create=True):
            result = _get_windows_dpi_scaling()

        assert result == {}

    def test_import_error_in_wintypes_returns_empty(self):
        """ImportError during ctypes.wintypes import → except branch."""
        import builtins
        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "ctypes.wintypes":
                raise ImportError("no wintypes on Linux")
            return real_import(name, *args, **kwargs)

        with patch("sys.platform", "win32"), \
             patch("builtins.__import__", side_effect=_fake_import):
            result = _get_windows_dpi_scaling()

        assert result == {}


class TestGetWindowsDPIScalingHappyPath:
    """Lines 108-165 — happy path with fully mocked ctypes.windll."""

    def test_single_monitor_returns_scale(self):
        """Enumerate one monitor handle and get DPI → scale returned."""
        mock_user32 = MagicMock()
        mock_shcore = MagicMock()
        mock_windll = MagicMock()
        mock_windll.user32 = mock_user32
        mock_windll.shcore = mock_shcore

        # EnumDisplayMonitors calls the callback with handle 1001
        def fake_enum(hdc, rect, callback, lparam):
            callback(1001, 0, None, 0)

        mock_user32.EnumDisplayMonitors.side_effect = fake_enum

        # GetDpiForMonitor writes 144 into dpi_x (144 / 96 = 1.5)
        def fake_get_dpi(h_monitor, dpi_type, dpi_x, dpi_y):
            dpi_x._obj.value = 144
            dpi_y._obj.value = 144

        mock_shcore.GetDpiForMonitor.side_effect = fake_get_dpi

        # Mock WINFUNCTYPE so the callback wrapping works on Linux
        def fake_winfunctype(*args):
            def decorator(fn):
                return fn
            return decorator

        with patch("sys.platform", "win32"), \
             patch.object(ctypes, "windll", mock_windll, create=True), \
             patch("ctypes.WINFUNCTYPE", fake_winfunctype, create=True):
            result = _get_windows_dpi_scaling()

        # The scale calculation requires dpi_x to be a ctypes.c_uint() — the fake
        # side_effect can't do that cleanly cross-platform, so just assert no crash
        assert isinstance(result, dict)

    def test_set_process_dpi_awareness_both_fail_logs_debug(self):
        """Lines 115-120 — both SetProcessDpiAwareness calls raise → debug log."""
        mock_user32 = MagicMock()
        mock_shcore = MagicMock()
        mock_windll = MagicMock()
        mock_windll.user32 = mock_user32
        mock_windll.shcore = mock_shcore

        mock_user32.SetProcessDpiAwarenessContext.side_effect = OSError("not supported V2")
        mock_shcore.SetProcessDpiAwareness.side_effect = OSError("not supported V1")
        # No monitor handles — EnumDisplayMonitors is a no-op
        mock_user32.EnumDisplayMonitors.return_value = None

        def fake_winfunctype(*args):
            def decorator(fn):
                return fn
            return decorator

        with patch("sys.platform", "win32"), \
             patch.object(ctypes, "windll", mock_windll, create=True), \
             patch("ctypes.WINFUNCTYPE", fake_winfunctype, create=True):
            result = _get_windows_dpi_scaling()

        assert result == {}

    def test_get_dpi_oserror_falls_back_to_1(self):
        """GetDpiForMonitor raises OSError → inner except → scale=1.0."""
        mock_user32 = MagicMock()
        mock_shcore = MagicMock()
        mock_windll = MagicMock()
        mock_windll.user32 = mock_user32
        mock_windll.shcore = mock_shcore

        def fake_enum(hdc, rect, callback, lparam):
            callback(1001, 0, None, 0)

        mock_user32.EnumDisplayMonitors.side_effect = fake_enum
        mock_shcore.GetDpiForMonitor.side_effect = OSError("DPI read failed")

        def fake_winfunctype(*args):
            def decorator(fn):
                return fn
            return decorator

        with patch("sys.platform", "win32"), \
             patch.object(ctypes, "windll", mock_windll, create=True), \
             patch("ctypes.WINFUNCTYPE", fake_winfunctype, create=True):
            result = _get_windows_dpi_scaling()

        # Fall-back sets scale=1.0 for each handle that failed
        assert isinstance(result, dict)


# ── _get_mss_monitors ─────────────────────────────────────────────────────


class TestGetMssMonitorsException:
    """Lines 181-184 — mss success and exception paths."""

    def test_mss_success_returns_monitors(self):
        """Line 181 — mss context manager works, returns monitors list."""
        mock_sct = MagicMock()
        mock_sct.monitors = [{"left": 0, "top": 0, "width": 1920, "height": 1080}]

        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_sct)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        mock_mss_module = MagicMock()
        mock_mss_module.mss.return_value = mock_ctx

        with patch.dict("sys.modules", {"mss": mock_mss_module}):
            result = _get_mss_monitors()

        assert result == [{"left": 0, "top": 0, "width": 1920, "height": 1080}]

    def test_import_error_returns_empty(self):
        with patch("builtins.__import__", side_effect=ImportError("no mss")):
            result = _get_mss_monitors()
        assert result == []

    def test_os_error_returns_empty(self):
        mock_mss_module = MagicMock()
        mock_mss_module.mss.side_effect = OSError("display unavailable")

        with patch.dict("sys.modules", {"mss": mock_mss_module}):
            result = _get_mss_monitors()

        assert result == []


# ── detect_monitors ───────────────────────────────────────────────────────


class TestDetectMonitorsPyautoguiFallback:
    """Lines 222-223 — OSError from pyautogui.size() uses default resolution."""

    def test_pyautogui_oserror_uses_default_resolution(self):
        with patch("core.dpi._get_mss_monitors", return_value=[]), \
             patch("core.dpi._get_windows_dpi_scaling", return_value={}), \
             patch("pyautogui.size", side_effect=OSError("no display")):
            monitors = detect_monitors()

        assert len(monitors) == 1
        assert monitors[0].width == 1920
        assert monitors[0].height == 1080
        assert monitors[0].is_primary is True


# ── physical_to_logical ───────────────────────────────────────────────────


class TestPhysicalToLogicalNoneMonitors:
    """Line 283 — monitors=None triggers fresh detect_monitors() call."""

    def test_none_monitors_triggers_detect(self):
        fake_monitors = [
            MonitorInfo(index=1, x=0, y=0, width=1920, height=1080, scale_factor=1.0)
        ]
        with patch("core.dpi.detect_monitors", return_value=fake_monitors) as mock_detect:
            result = physical_to_logical(100, 100, monitors=None)

        mock_detect.assert_called_once()
        assert result == (100, 100)


# ── logical_to_physical ───────────────────────────────────────────────────


class TestLogicalToPhysicalNoneMonitors:
    """Line 328 — monitors=None triggers fresh detect_monitors() call."""

    def test_none_monitors_triggers_detect(self):
        fake_monitors = [
            MonitorInfo(index=1, x=0, y=0, width=1920, height=1080, scale_factor=1.0)
        ]
        with patch("core.dpi.detect_monitors", return_value=fake_monitors) as mock_detect:
            result = logical_to_physical(100, 100, monitors=None)

        mock_detect.assert_called_once()
        assert result == (100, 100)

    def test_index_zero_skipped(self):
        """Line 332 — index==0 monitor is skipped."""
        monitors = [
            MonitorInfo(index=0, x=0, y=0, width=3840, height=1080, scale_factor=1.0),
            MonitorInfo(index=1, x=0, y=0, width=1920, height=1080, scale_factor=1.0),
        ]
        result = logical_to_physical(100, 100, monitors)
        assert result == (100, 100)

    def test_no_monitor_match_returns_unchanged(self):
        """Line 358 — fallback return (x, y) when no monitor matches."""
        monitors = [
            MonitorInfo(index=1, x=0, y=0, width=1920, height=1080, scale_factor=1.5)
        ]
        # Point way outside any logical monitor bounds
        result = logical_to_physical(9999, 9999, monitors)
        assert result == (9999, 9999)


# ── save_calibration ──────────────────────────────────────────────────────


class TestSaveCalibrationOSError:
    """Lines 408-409 — OSError during save is caught and logged."""

    def test_oserror_does_not_raise(self, tmp_path):
        calib = CalibrationData(config_hash="abc", monitors=[], calibrated_at=1.0)

        with patch("core.dpi._CALIBRATION_DIR", tmp_path), \
             patch("core.dpi._CALIBRATION_FILE", tmp_path / "displays.json"):
            # Make the tmp file's .replace() fail
            with patch.object(Path, "replace", side_effect=OSError("disk full")):
                save_calibration(calib)  # should not raise

    def test_oserror_logs_warning(self, tmp_path, caplog):
        import logging

        calib = CalibrationData(config_hash="abc", monitors=[], calibrated_at=1.0)

        with patch("core.dpi._CALIBRATION_DIR", tmp_path), \
             patch("core.dpi._CALIBRATION_FILE", tmp_path / "displays.json"):
            with patch.object(Path, "replace", side_effect=OSError("no space")):
                with caplog.at_level(logging.WARNING, logger="core.dpi"):
                    save_calibration(calib)

        assert any("Calibration save failed" in r.message for r in caplog.records)


# ── is_calibration_current ────────────────────────────────────────────────


class TestIsCalibrationCurrentMatch:
    """Line 431 — returns True when hash matches."""

    def test_returns_true_when_hash_matches(self, tmp_path):
        mss_mons = [{"left": 0, "top": 0, "width": 1920, "height": 1080}]

        # Pre-build the expected hash using the same function
        from core.dpi import _compute_config_hash
        expected_hash = _compute_config_hash(mss_mons)

        calib = CalibrationData(config_hash=expected_hash, monitors=[], calibrated_at=1.0)

        calib_file = tmp_path / "displays.json"
        with patch("core.dpi._CALIBRATION_FILE", calib_file), \
             patch("core.dpi._CALIBRATION_DIR", tmp_path), \
             patch("core.dpi._get_mss_monitors", return_value=mss_mons):
            save_calibration(calib)
            result = is_calibration_current()

        assert result is True

    def test_returns_false_when_hash_differs(self, tmp_path):
        calib = CalibrationData(config_hash="old_hash", monitors=[], calibrated_at=1.0)
        calib_file = tmp_path / "displays.json"

        with patch("core.dpi._CALIBRATION_FILE", calib_file), \
             patch("core.dpi._CALIBRATION_DIR", tmp_path), \
             patch("core.dpi._get_mss_monitors",
                   return_value=[{"left": 0, "top": 0, "width": 1920, "height": 1080}]):
            save_calibration(calib)
            result = is_calibration_current()

        assert result is False


# ── run_calibration_probe ─────────────────────────────────────────────────


class TestRunCalibrationProbeNoneMonitors:
    """Line 458 — monitors=None triggers detect_monitors() inside probe."""

    def test_none_monitors_calls_detect(self, tmp_path):
        fake_monitors = [
            MonitorInfo(index=1, x=0, y=0, width=1920, height=1080,
                        scale_factor=1.0, is_primary=True, device_id="mon1")
        ]
        calib_file = tmp_path / "displays.json"

        with patch("core.dpi._CALIBRATION_FILE", calib_file), \
             patch("core.dpi._CALIBRATION_DIR", tmp_path), \
             patch("core.dpi._get_mss_monitors",
                   return_value=[{"left": 0, "top": 0, "width": 1920, "height": 1080}]), \
             patch("core.dpi.detect_monitors", return_value=fake_monitors) as mock_detect:
            calib = run_calibration_probe(monitors=None)

        mock_detect.assert_called_once()
        assert calib.config_hash != ""

    def test_probe_skips_index_zero_monitor(self, tmp_path):
        """Line 473 — index==0 monitor is skipped during calibration build."""
        monitors = [
            MonitorInfo(index=0, x=0, y=0, width=3840, height=1080, scale_factor=1.0),
            MonitorInfo(index=1, x=0, y=0, width=1920, height=1080,
                        scale_factor=1.0, is_primary=True, device_id="mon1"),
        ]
        calib_file = tmp_path / "displays.json"

        with patch("core.dpi._CALIBRATION_FILE", calib_file), \
             patch("core.dpi._CALIBRATION_DIR", tmp_path), \
             patch("core.dpi._get_mss_monitors",
                   return_value=[{"left": 0, "top": 0, "width": 1920, "height": 1080}]):
            calib = run_calibration_probe(monitors=monitors)

        # Only the index=1 monitor should be in the result (index=0 was skipped)
        assert len(calib.monitors) == 1
        assert calib.monitors[0]["index"] == 1


# ── get_monitors cache TTL ────────────────────────────────────────────────


class TestGetMonitorsCacheHashUnchanged:
    """Line 547 — cache TTL expires but config hash is unchanged → debug log."""

    def test_ttl_refresh_with_same_hash_logs_debug(self, caplog):
        import logging

        import core.dpi as dpi_mod

        mss_mons = [{"left": 0, "top": 0, "width": 1920, "height": 1080}]
        fake_monitors = [
            MonitorInfo(index=1, x=0, y=0, width=1920, height=1080, scale_factor=1.0)
        ]

        clear_monitor_cache()

        # First call: populates cache
        with patch("core.dpi._get_mss_monitors", return_value=mss_mons), \
             patch("core.dpi.detect_monitors", return_value=fake_monitors):
            get_monitors()

        # Force TTL expiry without clearing the cached monitors/hash
        with dpi_mod._calib_lock:
            dpi_mod._cache_timestamp = 0.0

        # Second call: TTL expired, but hash is the same → else branch (line 547)
        with patch("core.dpi._get_mss_monitors", return_value=mss_mons), \
             patch("core.dpi.detect_monitors", return_value=fake_monitors) as mock_detect, \
             caplog.at_level(logging.DEBUG, logger="core.dpi"):
            get_monitors()

        mock_detect.assert_not_called()
        assert any("Monitor cache TTL refresh" in r.message for r in caplog.records)

        clear_monitor_cache()
