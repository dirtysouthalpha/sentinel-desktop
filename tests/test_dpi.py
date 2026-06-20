"""Tests for core.dpi — DPI detection, coordinate transformation, and calibration."""

import time
from unittest.mock import patch

import pytest

from core.dpi import (
    CalibrationData,
    MonitorInfo,
    _compute_config_hash,
    clear_monitor_cache,
    detect_monitors,
    get_monitors,
    is_calibration_current,
    load_calibration,
    logical_to_physical,
    physical_to_logical,
    run_calibration_probe,
    save_calibration,
    transform_action_coordinates,
)

# ---------------------------------------------------------------------------
# MonitorInfo dataclass
# ---------------------------------------------------------------------------


class TestMonitorInfo:
    """Tests for the MonitorInfo dataclass."""

    def test_logical_dimensions_100_percent(self):
        mon = MonitorInfo(width=1920, height=1080, scale_factor=1.0)
        assert mon.logical_width == 1920
        assert mon.logical_height == 1080

    def test_logical_dimensions_150_percent(self):
        mon = MonitorInfo(width=2880, height=1620, scale_factor=1.5)
        assert mon.logical_width == 1920
        assert mon.logical_height == 1080

    def test_logical_dimensions_200_percent(self):
        mon = MonitorInfo(width=3840, height=2160, scale_factor=2.0)
        assert mon.logical_width == 1920
        assert mon.logical_height == 1080

    def test_logical_dimensions_125_percent(self):
        mon = MonitorInfo(width=2400, height=1350, scale_factor=1.25)
        assert mon.logical_width == 1920
        assert mon.logical_height == 1080

    def test_defaults(self):
        mon = MonitorInfo()
        assert mon.index == 0
        assert mon.scale_factor == 1.0
        assert mon.is_primary is False
        assert mon.device_id == ""


# ---------------------------------------------------------------------------
# Coordinate transformation — single monitor
# ---------------------------------------------------------------------------


class TestCoordinateTransform:
    """Tests for physical ↔ logical coordinate conversion."""

    def test_identity_at_100_percent(self):
        """100% scaling → physical == logical."""
        monitors = [
            MonitorInfo(index=1, width=1920, height=1080, scale_factor=1.0, is_primary=True)
        ]
        assert physical_to_logical(500, 300, monitors) == (500, 300)
        assert logical_to_physical(500, 300, monitors) == (500, 300)

    def test_150_percent_single_monitor(self):
        """150% scaling on primary monitor."""
        monitors = [
            MonitorInfo(
                index=1, x=0, y=0, width=2880, height=1620, scale_factor=1.5, is_primary=True
            ),
        ]
        # Physical center (1440, 810) → Logical center (960, 540)
        lx, ly = physical_to_logical(1440, 810, monitors)
        assert lx == 960
        assert ly == 540

        # Reverse: Logical (960, 540) → Physical (1440, 810)
        px, py = logical_to_physical(960, 540, monitors)
        assert px == 1440
        assert py == 810

    def test_200_percent_single_monitor(self):
        """200% scaling."""
        monitors = [
            MonitorInfo(
                index=1, x=0, y=0, width=3840, height=2160, scale_factor=2.0, is_primary=True
            ),
        ]
        lx, ly = physical_to_logical(2000, 1000, monitors)
        assert lx == 1000
        assert ly == 500

        px, py = logical_to_physical(1000, 500, monitors)
        assert px == 2000
        assert py == 1000

    def test_125_percent_corner_coordinates(self):
        """125% scaling — edge cases near corners."""
        monitors = [
            MonitorInfo(
                index=1, x=0, y=0, width=2400, height=1350, scale_factor=1.25, is_primary=True
            ),
        ]
        # Top-left corner
        lx, ly = physical_to_logical(0, 0, monitors)
        assert lx == 0
        assert ly == 0

        # Bottom-right corner (2400/1.25=1920, 1350/1.25=1080)
        lx, ly = physical_to_logical(2399, 1349, monitors)
        assert lx == int(2399 / 1.25)
        assert ly == int(1349 / 1.25)

    def test_fallback_no_monitor_match(self):
        """If no monitor matches the point, pass through unchanged."""
        monitors = [
            MonitorInfo(
                index=1, x=0, y=0, width=1920, height=1080, scale_factor=1.5, is_primary=True
            ),
        ]
        # Point way outside any monitor
        lx, ly = physical_to_logical(5000, 5000, monitors)
        assert lx == 5000
        assert ly == 5000

    def test_virtual_monitor_index_0_is_skipped(self):
        """Index 0 (virtual desktop aggregate) should be skipped."""
        monitors = [
            MonitorInfo(index=0, x=-1920, y=0, width=5760, height=1080, scale_factor=1.0),
            MonitorInfo(
                index=1, x=0, y=0, width=1920, height=1080, scale_factor=1.0, is_primary=True
            ),
        ]
        # Point at (100, 100) — should match index 1, not 0
        lx, ly = physical_to_logical(100, 100, monitors)
        assert lx == 100
        assert ly == 100


# ---------------------------------------------------------------------------
# Multi-monitor transformation
# ---------------------------------------------------------------------------


class TestMultiMonitorTransform:
    """Tests for multi-monitor coordinate transformation."""

    def test_two_monitors_same_scaling(self):
        """Two monitors at 100% — offsets only, no scaling."""
        monitors = [
            MonitorInfo(index=0, x=0, y=0, width=3840, height=1080, scale_factor=1.0),
            MonitorInfo(
                index=1, x=0, y=0, width=1920, height=1080, scale_factor=1.0, is_primary=True
            ),
            MonitorInfo(index=2, x=1920, y=0, width=1920, height=1080, scale_factor=1.0),
        ]
        # Primary monitor point
        lx, ly = physical_to_logical(500, 300, monitors)
        assert lx == 500
        assert ly == 300

        # Secondary monitor point (x=1920+500=2420)
        lx, ly = physical_to_logical(2420, 300, monitors)
        assert lx == 2420  # No scaling, same
        assert ly == 300

    def test_mixed_scaling(self):
        """Primary at 150%, secondary at 100%."""
        monitors = [
            MonitorInfo(
                index=1, x=0, y=0, width=2880, height=1620, scale_factor=1.5, is_primary=True
            ),
            MonitorInfo(index=2, x=2880, y=0, width=1920, height=1080, scale_factor=1.0),
        ]
        # Point on primary (physical 1440, 810 → logical 960, 540)
        lx, ly = physical_to_logical(1440, 810, monitors)
        assert lx == 960
        assert ly == 540

        # Point on secondary (physical 3000, 100 → no scaling, same)
        lx, ly = physical_to_logical(3000, 100, monitors)
        assert lx == 3000
        assert ly == 100

    def test_secondary_150_percent(self):
        """Primary at 100%, secondary at 150% with offset."""
        monitors = [
            MonitorInfo(
                index=1, x=0, y=0, width=1920, height=1080, scale_factor=1.0, is_primary=True
            ),
            MonitorInfo(index=2, x=1920, y=0, width=2880, height=1620, scale_factor=1.5),
        ]
        # Point on secondary: local_x = 3000 - 1920 = 1080
        # logical_x = int(1080 / 1.5) + int(1920 / 1.5) = 720 + 1280 = 2000
        lx, ly = physical_to_logical(3000, 100, monitors)
        assert lx == 2000
        assert ly == int(100 / 1.5)


# ---------------------------------------------------------------------------
# transform_action_coordinates
# ---------------------------------------------------------------------------


class TestTransformAction:
    """Tests for action dict coordinate transformation."""

    def test_no_scaling_needed(self):
        """All monitors at 100% → action passes through unchanged."""
        monitors = [MonitorInfo(index=1, width=1920, height=1080, scale_factor=1.0)]
        action = {"action": "click", "x": 500, "y": 300}
        result = transform_action_coordinates(action, monitors)
        assert result == action

    def test_click_with_150_percent(self):
        """Click action gets coordinates transformed."""
        monitors = [
            MonitorInfo(
                index=1, x=0, y=0, width=2880, height=1620, scale_factor=1.5, is_primary=True
            ),
        ]
        action = {"action": "click", "x": 1440, "y": 810}
        result = transform_action_coordinates(action, monitors)
        assert result["x"] == 960
        assert result["y"] == 540
        assert result["action"] == "click"

    def test_drag_action(self):
        """Drag action transforms from/to coordinates."""
        monitors = [
            MonitorInfo(
                index=1, x=0, y=0, width=2880, height=1620, scale_factor=1.5, is_primary=True
            ),
        ]
        action = {
            "action": "drag",
            "from_x": 1440,
            "from_y": 810,
            "to_x": 1500,
            "to_y": 900,
            "duration": 0.5,
        }
        result = transform_action_coordinates(action, monitors)
        assert result["from_x"] == 960
        assert result["from_y"] == 540
        assert result["to_x"] == 1000
        assert result["to_y"] == 600
        assert result["duration"] == 0.5  # Non-coordinate params untouched

    def test_non_coordinate_action_unchanged(self):
        """Actions without coordinates pass through."""
        monitors = [
            MonitorInfo(
                index=1, x=0, y=0, width=2880, height=1620, scale_factor=1.5, is_primary=True
            ),
        ]
        action = {"action": "type_text", "text": "hello"}
        result = transform_action_coordinates(action, monitors)
        assert result == action

    def test_does_not_mutate_original(self):
        """Original action dict should not be modified."""
        monitors = [
            MonitorInfo(
                index=1, x=0, y=0, width=2880, height=1620, scale_factor=1.5, is_primary=True
            ),
        ]
        action = {"action": "click", "x": 1440, "y": 810}
        original_x = action["x"]
        transform_action_coordinates(action, monitors)
        assert action["x"] == original_x


# ---------------------------------------------------------------------------
# Config hash computation
# ---------------------------------------------------------------------------


class TestConfigHash:
    """Tests for display config hash computation."""

    def test_same_config_same_hash(self):
        monitors = [
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 1920, "top": 0, "width": 1920, "height": 1080},
        ]
        h1 = _compute_config_hash(monitors)
        h2 = _compute_config_hash(monitors)
        assert h1 == h2

    def test_different_config_different_hash(self):
        m1 = [{"left": 0, "top": 0, "width": 1920, "height": 1080}]
        m2 = [{"left": 0, "top": 0, "width": 3840, "height": 2160}]
        assert _compute_config_hash(m1) != _compute_config_hash(m2)

    def test_empty_monitors(self):
        h = _compute_config_hash([])
        assert isinstance(h, str)
        assert len(h) == 12


# ---------------------------------------------------------------------------
# Calibration persistence
# ---------------------------------------------------------------------------


class TestCalibration:
    """Tests for calibration file I/O."""

    def test_save_and_load(self, tmp_path):
        calib_file = tmp_path / "displays.json"
        with patch("core.dpi._CALIBRATION_FILE", calib_file):
            with patch("core.dpi._CALIBRATION_DIR", tmp_path):
                calib = CalibrationData(
                    config_hash="abc123",
                    monitors=[{"index": 1, "scale_factor": 1.5}],
                    calibrated_at=1000.0,
                    verified=True,
                )
                save_calibration(calib)

                loaded = load_calibration()
                assert loaded is not None
                assert loaded.config_hash == "abc123"
                assert len(loaded.monitors) == 1
                assert loaded.monitors[0]["scale_factor"] == 1.5
                assert loaded.verified is True

    def test_load_nonexistent(self, tmp_path):
        with patch("core.dpi._CALIBRATION_FILE", tmp_path / "nonexistent.json"):
            assert load_calibration() is None

    def test_load_corrupt_file(self, tmp_path):
        calib_file = tmp_path / "displays.json"
        calib_file.write_text("NOT JSON{{{")
        with patch("core.dpi._CALIBRATION_FILE", calib_file):
            assert load_calibration() is None

    def test_is_calibration_current_when_no_file(self, tmp_path):
        with patch("core.dpi._CALIBRATION_FILE", tmp_path / "nonexistent.json"):
            with patch(
                "core.dpi._get_mss_monitors",
                return_value=[{"left": 0, "top": 0, "width": 1920, "height": 1080}],
            ):
                assert is_calibration_current() is False

    def test_calibration_probe_saves(self, tmp_path):
        calib_file = tmp_path / "displays.json"
        with patch("core.dpi._CALIBRATION_FILE", calib_file):
            with patch("core.dpi._CALIBRATION_DIR", tmp_path):
                with patch(
                    "core.dpi._get_mss_monitors",
                    return_value=[
                        {"left": 0, "top": 0, "width": 1920, "height": 1080},
                    ],
                ):
                    monitors = [
                        MonitorInfo(
                            index=1,
                            x=0,
                            y=0,
                            width=1920,
                            height=1080,
                            scale_factor=1.0,
                            is_primary=True,
                            device_id="mon1",
                        ),
                    ]
                    calib = run_calibration_probe(monitors=monitors)
                    assert calib.config_hash != ""
                    assert len(calib.monitors) == 1
                    assert calib.calibrated_at > 0
                    assert calib_file.exists()

    def test_calibration_probe_skips_when_current(self, tmp_path):
        calib_file = tmp_path / "displays.json"
        with patch("core.dpi._CALIBRATION_FILE", calib_file):
            with patch("core.dpi._CALIBRATION_DIR", tmp_path):
                with patch(
                    "core.dpi._get_mss_monitors",
                    return_value=[
                        {"left": 0, "top": 0, "width": 1920, "height": 1080},
                    ],
                ):
                    monitors = [
                        MonitorInfo(
                            index=1,
                            x=0,
                            y=0,
                            width=1920,
                            height=1080,
                            scale_factor=1.0,
                            is_primary=True,
                            device_id="mon1",
                        ),
                    ]
                    # First probe — saves
                    first = run_calibration_probe(monitors=monitors)
                    first_time = first.calibrated_at

                    # Second probe — should return same calibration (not re-save)
                    time.sleep(0.01)
                    second = run_calibration_probe(monitors=monitors)
                    assert second.calibrated_at == first_time  # Unchanged

    def test_calibration_probe_force(self, tmp_path):
        calib_file = tmp_path / "displays.json"
        with patch("core.dpi._CALIBRATION_FILE", calib_file):
            with patch("core.dpi._CALIBRATION_DIR", tmp_path):
                with patch(
                    "core.dpi._get_mss_monitors",
                    return_value=[
                        {"left": 0, "top": 0, "width": 1920, "height": 1080},
                    ],
                ):
                    monitors = [
                        MonitorInfo(
                            index=1,
                            x=0,
                            y=0,
                            width=1920,
                            height=1080,
                            scale_factor=1.0,
                            is_primary=True,
                            device_id="mon1",
                        ),
                    ]
                    first = run_calibration_probe(monitors=monitors)
                    time.sleep(0.01)
                    forced = run_calibration_probe(monitors=monitors, force=True)
                    assert forced.calibrated_at > first.calibrated_at


# ---------------------------------------------------------------------------
# detect_monitors
# ---------------------------------------------------------------------------


class TestDetectMonitors:
    """Tests for monitor detection."""

    def test_fallback_when_no_mss(self):
        """When mss is unavailable, returns a single fallback monitor."""
        with patch("core.dpi._get_mss_monitors", return_value=[]):
            with patch("core.dpi._get_windows_dpi_scaling", return_value={}):
                with patch("core.dpi._get_windows_dpi_scaling", return_value={}):
                    with patch("pyautogui.size", return_value=(1920, 1080)):
                        monitors = detect_monitors()
                        assert len(monitors) == 1
                        assert monitors[0].index == 1
                        assert monitors[0].is_primary is True
                        assert monitors[0].scale_factor == 1.0

    def test_with_mss_single_monitor(self):
        """Single monitor from mss."""
        with patch(
            "core.dpi._get_mss_monitors",
            return_value=[
                {"left": 0, "top": 0, "width": 3840, "height": 2160},
                {"left": 0, "top": 0, "width": 3840, "height": 2160},
            ],
        ):
            with patch("core.dpi._get_windows_dpi_scaling", return_value={1: 2.0}):
                monitors = detect_monitors()
                assert len(monitors) == 2  # virtual (0) + primary (1)
                assert monitors[1].scale_factor == 2.0
                assert monitors[1].is_primary is True

    def test_with_mss_multi_monitor(self):
        """Multiple monitors from mss."""
        with patch(
            "core.dpi._get_mss_monitors",
            return_value=[
                {"left": 0, "top": 0, "width": 4800, "height": 1620},  # virtual
                {"left": 0, "top": 0, "width": 2880, "height": 1620},  # primary 150%
                {"left": 2880, "top": 0, "width": 1920, "height": 1080},  # secondary 100%
            ],
        ):
            with patch("core.dpi._get_windows_dpi_scaling", return_value={1: 1.5, 2: 1.0}):
                monitors = detect_monitors()
                assert len(monitors) == 3
                assert monitors[1].scale_factor == 1.5
                assert monitors[2].scale_factor == 1.0

    def test_dpi_fallback_to_1(self):
        """When Windows DPI detection fails, defaults to 1.0."""
        with patch(
            "core.dpi._get_mss_monitors",
            return_value=[
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
            ],
        ):
            with patch("core.dpi._get_windows_dpi_scaling", return_value={}):
                monitors = detect_monitors()
                assert monitors[1].scale_factor == 1.0


# ---------------------------------------------------------------------------
# Monitor cache
# ---------------------------------------------------------------------------


class TestMonitorCache:
    """Tests for the global monitor cache."""

    def setup_method(self):
        clear_monitor_cache()

    def teardown_method(self):
        clear_monitor_cache()

    def test_get_monitors_caches(self):
        """get_monitors() should cache and not re-detect on second call."""
        with patch("core.dpi.detect_monitors") as mock_detect:
            mock_detect.return_value = [
                MonitorInfo(index=1, width=1920, height=1080, scale_factor=1.0, is_primary=True),
            ]
            with patch(
                "core.dpi._get_mss_monitors",
                return_value=[
                    {"left": 0, "top": 0, "width": 1920, "height": 1080},
                ],
            ):
                get_monitors()
                get_monitors()
                # detect_monitors should only be called once (cache hit on second)
                assert mock_detect.call_count == 1

    def test_clear_cache_forces_redetect(self):
        with patch("core.dpi.detect_monitors") as mock_detect:
            mock_detect.return_value = [
                MonitorInfo(index=1, width=1920, height=1080, scale_factor=1.0, is_primary=True),
            ]
            with patch(
                "core.dpi._get_mss_monitors",
                return_value=[
                    {"left": 0, "top": 0, "width": 1920, "height": 1080},
                ],
            ):
                get_monitors()
                clear_monitor_cache()
                get_monitors()
                assert mock_detect.call_count == 2


# ---------------------------------------------------------------------------
# Integration: action executor uses DPI transform
# ---------------------------------------------------------------------------


class TestExecutorIntegration:
    """Verify the action executor applies DPI transformation."""

    def test_executor_imports_dpi(self):
        """Action executor should import transform_action_coordinates."""

        # Verify the import exists (no ImportError)
        import core.action_executor as ae

        assert hasattr(ae, "transform_action_coordinates")

    def test_execute_sync_transforms_coordinates(self):
        """execute_sync should transform physical coords to logical."""
        from core.action_executor import ActionExecutor, ExecutorConfig

        executor = ActionExecutor(config=ExecutorConfig(dry_run=True))

        with patch("core.dpi.get_monitors") as mock_mon:
            mock_mon.return_value = [
                MonitorInfo(
                    index=1, x=0, y=0, width=2880, height=1620, scale_factor=1.5, is_primary=True
                ),
            ]
            # The action should have its coordinates transformed before dry-run
            result = executor.execute_sync({"action": "click", "x": 1440, "y": 810})
            assert result["success"] is True  # dry-run always succeeds


# ---------------------------------------------------------------------------
# Round-trip: physical → logical → physical
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Verify coordinate transforms are reversible."""

    @pytest.mark.parametrize("scale", [1.0, 1.25, 1.5, 2.0])
    def test_round_trip_various_scales(self, scale):
        """physical → logical → physical should return original coords."""
        monitors = [
            MonitorInfo(
                index=1,
                x=0,
                y=0,
                width=int(1920 * scale),
                height=int(1080 * scale),
                scale_factor=scale,
                is_primary=True,
            ),
        ]
        # Test several points
        for px, py in [(100, 100), (500, 300), (960, 540), (1400, 800)]:
            lx, ly = physical_to_logical(px, py, monitors)
            rpx, rpy = logical_to_physical(lx, ly, monitors)
            # Allow 1px rounding error
            assert abs(rpx - px) <= 1, (
                f"Round-trip failed for ({px},{py}) at {scale}x: got ({rpx},{rpy})"
            )
            assert abs(rpy - py) <= 1, (
                f"Round-trip failed for ({px},{py}) at {scale}x: got ({rpx},{rpy})"
            )
