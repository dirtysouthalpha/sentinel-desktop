"""
Tests for core/dashboard.py — System Dashboard API.

Covers CPU, memory, disk, GPU, log counting helpers, and all three
FastAPI endpoints with psutil mocked appropriately.
"""

from __future__ import annotations

import builtins
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Helper mocks ──────────────────────────────────────────────────────────


class _FakeCpuFreq:
    """Minimal stand-in for psutil.cpu_freq() result."""

    def __init__(self, current: float = 3400.0):
        self.current = current


class _FakeVirtualMem:
    """Minimal stand-in for psutil.virtual_memory() result."""

    def __init__(self, total=32 * 1024**3, used=16 * 1024**3, available=16 * 1024**3, percent=50.0):
        self.total = total
        self.used = used
        self.available = available
        self.percent = percent


class _FakePartition:
    def __init__(self, mountpoint="/"):
        self.mountpoint = mountpoint


class _FakeUsage:
    def __init__(self, total=500 * 1024**3, used=250 * 1024**3, free=250 * 1024**3, percent=50.0):
        self.total = total
        self.used = used
        self.free = free
        self.percent = percent


def _make_psutil(
    cpu_percent=45.0,
    cpu_count_physical=8,
    cpu_count_logical=16,
    cpu_freq=_FakeCpuFreq(),
    virtual_mem=None,
    disk_partitions=None,
    disk_usage=None,
):
    """Build a lightweight psutil stub."""
    mod = MagicMock()
    mod.cpu_percent.return_value = cpu_percent
    mod.cpu_count.side_effect = lambda logical=True: cpu_count_logical if logical else cpu_count_physical
    mod.cpu_freq.return_value = cpu_freq
    mod.virtual_memory.return_value = virtual_mem or _FakeVirtualMem()
    if disk_partitions is not None:
        mod.disk_partitions.return_value = disk_partitions
    else:
        mod.disk_partitions.return_value = [_FakePartition()]
    if disk_usage is not None:
        mod.disk_usage.side_effect = disk_usage
    else:
        mod.disk_usage.return_value = _FakeUsage()
    return mod


@contextmanager
def _no_psutil():
    """Make an in-function ``import psutil`` raise ImportError.

    The dashboard helpers import psutil lazily inside each function, so the
    ``except ImportError`` fallback only fires when the import statement
    itself fails. Patching ``builtins.__import__`` intercepts the statement
    regardless of whether psutil is already cached in ``sys.modules``.
    """
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("psutil unavailable")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        yield


# ── Tests: _get_cpu_info ──────────────────────────────────────────────────


class TestGetCpuInfo:
    """Tests for core.dashboard._get_cpu_info."""

    def test_returns_percent_and_counts(self):
        import core.dashboard as dash

        fake_psutil = _make_psutil()
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            result = dash._get_cpu_info()
        assert result["percent"] == 45.0
        assert result["count_physical"] == 8
        assert result["count_logical"] == 16

    def test_includes_freq_when_available(self):
        import core.dashboard as dash

        fake_psutil = _make_psutil(cpu_freq=_FakeCpuFreq(3600.0))
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            result = dash._get_cpu_info()
        assert result["freq_current"] == 3600.0

    def test_freq_none_omitted(self):
        import core.dashboard as dash

        fake_psutil = _make_psutil()
        fake_psutil.cpu_freq.return_value = None
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            result = dash._get_cpu_info()
        assert result["freq_current"] is None

    def test_fallback_when_no_psutil(self):
        import core.dashboard as dash

        # Genuinely trigger the ``except ImportError`` branch by making the
        # in-function ``import psutil`` fail.
        with _no_psutil():
            result = dash._get_cpu_info()
        assert result["percent"] == 0
        # On ImportError the logical-count falls back to platform.processor().
        assert "count_logical" in result


# ── Tests: _get_memory_info ───────────────────────────────────────────────


class TestGetMemoryInfo:
    """Tests for core.dashboard._get_memory_info."""

    def test_returns_memory_fields(self):
        import core.dashboard as dash

        mem = _FakeVirtualMem(total=64 * 1024**3, used=32 * 1024**3, available=32 * 1024**3, percent=50.0)
        fake_psutil = _make_psutil(virtual_mem=mem)
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            result = dash._get_memory_info()
        assert result["total_gb"] == 64.0
        assert result["percent"] == 50.0
        assert "used_gb" in result
        assert "available_gb" in result

    def test_fallback_when_no_psutil(self):
        import core.dashboard as dash

        with _no_psutil():
            result = dash._get_memory_info()
        assert result["total_gb"] == 0
        assert result["percent"] == 0


# ── Tests: _get_disk_info ─────────────────────────────────────────────────


class TestGetDiskInfo:
    """Tests for core.dashboard._get_disk_info."""

    def test_returns_disk_list(self):
        import core.dashboard as dash

        partitions = [_FakePartition("/"), _FakePartition("/home")]
        usage_map = {
            "/": _FakeUsage(total=500 * 1024**3, used=200 * 1024**3, free=300 * 1024**3, percent=40.0),
            "/home": _FakeUsage(total=1000 * 1024**3, used=600 * 1024**3, free=400 * 1024**3, percent=60.0),
        }
        fake_psutil = _make_psutil(disk_partitions=partitions, disk_usage=lambda mp: usage_map[mp])
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            result = dash._get_disk_info()
        assert len(result) == 2
        assert result[0]["mount"] == "/"
        assert result[0]["percent"] == 40.0
        assert result[1]["mount"] == "/home"
        assert result[1]["percent"] == 60.0

    def test_skips_partitions_with_permission_error(self):
        import core.dashboard as dash

        partitions = [_FakePartition("/"), _FakePartition("/restricted")]

        def usage_with_error(mp):
            if mp == "/restricted":
                raise PermissionError("nope")
            return _FakeUsage()

        fake_psutil = _make_psutil(disk_partitions=partitions, disk_usage=usage_with_error)
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            result = dash._get_disk_info()
        assert len(result) == 1
        assert result[0]["mount"] == "/"

    def test_fallback_when_no_psutil(self):
        import core.dashboard as dash

        with _no_psutil():
            result = dash._get_disk_info()
        assert result == []


# ── Tests: _get_gpu_info ──────────────────────────────────────────────────


class TestGetGpuInfo:
    """Tests for core.dashboard._get_gpu_info."""

    def test_parses_nvidia_smi_output(self):
        import core.dashboard as dash

        fake_result = MagicMock()
        fake_result.returncode = 0
        fake_result.stdout = "NVIDIA RTX 4090, 8192, 24576, 65, 85, 320.5\n"
        with patch("shutil.which", return_value="/usr/bin/nvidia-smi"), patch(
            "subprocess.run", return_value=fake_result
        ):
            result = dash._get_gpu_info()
        assert len(result) == 1
        assert result[0]["name"] == "NVIDIA RTX 4090"
        assert result[0]["memory_used_mb"] == 8192.0
        assert result[0]["temperature_c"] == 65.0

    def test_returns_empty_on_bad_exit(self):
        import core.dashboard as dash

        fake_result = MagicMock()
        fake_result.returncode = 1
        fake_result.stdout = ""
        with patch("subprocess.run", return_value=fake_result):
            result = dash._get_gpu_info()
        assert result == []

    def test_returns_empty_on_timeout(self):
        import core.dashboard as dash

        with patch("subprocess.run", side_effect=TimeoutError()):
            result = dash._get_gpu_info()
        assert result == []

    def test_skips_malformed_lines(self):
        import core.dashboard as dash

        fake_result = MagicMock()
        fake_result.returncode = 0
        # Only 3 fields — not enough for 6 expected columns
        fake_result.stdout = "GPU, 100, 200\n"
        with patch("subprocess.run", return_value=fake_result):
            result = dash._get_gpu_info()
        assert result == []


# ── Tests: _count_log_entries ─────────────────────────────────────────────


class TestCountLogEntries:
    """Tests for core.dashboard._count_log_entries."""

    def test_counts_json_files_in_log_dir(self, tmp_path):
        import core.dashboard as dash

        log_dir = tmp_path / ".sentinel" / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "a.json").write_text("{}")
        (log_dir / "b.json").write_text("{}")
        (log_dir / "c.txt").write_text("not a log")

        with patch.object(Path, "home", return_value=tmp_path):
            result = dash._count_log_entries()
        assert result["total_logs"] == 2

    def test_returns_zero_when_no_dir(self, tmp_path):
        import core.dashboard as dash

        with patch.object(Path, "home", return_value=tmp_path):
            result = dash._count_log_entries()
        assert result["total_logs"] == 0

    def test_returns_zero_on_exception(self):
        import core.dashboard as dash

        with patch.object(Path, "home", side_effect=OSError("boom")):
            result = dash._count_log_entries()
        assert result["total_logs"] == 0


# ── Tests: dashboard_overview endpoint ────────────────────────────────────


class TestDashboardOverview:
    """Tests for the /dashboard/overview endpoint."""

    @pytest.mark.asyncio
    async def test_overview_returns_structure(self):
        import core.dashboard as dash

        fake_psutil = _make_psutil()
        with patch.dict(sys.modules, {"psutil": fake_psutil}), \
             patch("subprocess.run", side_effect=FileNotFoundError("no nvidia")):
            result = await dash.dashboard_overview()
        assert "timestamp" in result
        assert "system" in result
        assert "cpu" in result
        assert "memory" in result
        assert "disks" in result
        assert "gpus" in result
        assert "logs" in result

    @pytest.mark.asyncio
    async def test_overview_uptime_format(self):
        import core.dashboard as dash

        fake_psutil = _make_psutil()
        # Set module start time to 3661 seconds ago
        with patch.dict(sys.modules, {"psutil": fake_psutil}), \
             patch.object(dash, "_start_time", time.time() - 3661), \
             patch("subprocess.run", side_effect=FileNotFoundError("no nvidia")):
            result = await dash.dashboard_overview()
        assert result["system"]["uptime_seconds"] >= 3661
        assert "1h" in result["system"]["uptime"]

    @pytest.mark.asyncio
    async def test_overview_platform_info(self):
        import platform

        import core.dashboard as dash

        fake_psutil = _make_psutil()
        with patch.dict(sys.modules, {"psutil": fake_psutil}), \
             patch("subprocess.run", side_effect=FileNotFoundError("no nvidia")):
            result = await dash.dashboard_overview()
        assert result["system"]["platform"] == platform.system()
        assert result["system"]["python_version"] == platform.python_version()


# ── Tests: health_check endpoint ──────────────────────────────────────────


class TestHealthCheck:
    """Tests for the /dashboard/health endpoint."""

    @pytest.mark.asyncio
    async def test_healthy_when_normal(self):
        import core.dashboard as dash

        fake_psutil = _make_psutil(cpu_percent=45.0)
        mem = _FakeVirtualMem(percent=40.0)
        fake_psutil.virtual_memory.return_value = mem
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            result = await dash.health_check()
        assert result["status"] == "healthy"
        assert result["issues"] == []

    @pytest.mark.asyncio
    async def test_warning_when_cpu_high(self):
        import core.dashboard as dash

        fake_psutil = _make_psutil(cpu_percent=95.0)
        mem = _FakeVirtualMem(percent=40.0)
        fake_psutil.virtual_memory.return_value = mem
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            result = await dash.health_check()
        assert result["status"] == "warning"
        assert any("CPU" in i for i in result["issues"])

    @pytest.mark.asyncio
    async def test_warning_when_memory_high(self):
        import core.dashboard as dash

        fake_psutil = _make_psutil(cpu_percent=30.0)
        mem = _FakeVirtualMem(percent=95.0)
        fake_psutil.virtual_memory.return_value = mem
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            result = await dash.health_check()
        assert result["status"] == "warning"
        assert any("Memory" in i for i in result["issues"])

    @pytest.mark.asyncio
    async def test_appends_to_health_checks(self):
        import core.dashboard as dash

        # Reset health checks list for test isolation
        original = dash._health_checks[:]
        try:
            dash._health_checks.clear()
            fake_psutil = _make_psutil()
            with patch.dict(sys.modules, {"psutil": fake_psutil}):
                await dash.health_check()
                await dash.health_check()
            assert len(dash._health_checks) == 2
        finally:
            dash._health_checks[:] = original

    @pytest.mark.asyncio
    async def test_trims_health_checks_over_100(self):
        import core.dashboard as dash

        original = dash._health_checks[:]
        try:
            dash._health_checks.clear()
            # Pre-fill 99 entries
            dash._health_checks.extend([{"status": "healthy"}] * 99)
            fake_psutil = _make_psutil()
            with patch.dict(sys.modules, {"psutil": fake_psutil}):
                await dash.health_check()
            # Should now have 100, no trim yet
            assert len(dash._health_checks) == 100
            # Next one triggers trim: append (101) -> trim to last 50
            await dash.health_check()
            assert len(dash._health_checks) == 50
        finally:
            dash._health_checks[:] = original


# ── Tests: metrics endpoint ───────────────────────────────────────────────


class TestMetrics:
    """Tests for the /dashboard/metrics endpoint."""

    @pytest.mark.asyncio
    async def test_returns_lightweight_metrics(self):
        import core.dashboard as dash

        mem = _FakeVirtualMem(percent=55.0, used=17.6 * 1024**3)
        fake_psutil = _make_psutil(cpu_percent=42.0)
        fake_psutil.virtual_memory.return_value = mem
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            result = await dash.metrics()
        assert result["cpu_percent"] == 42.0
        assert result["memory_percent"] == 55.0
        assert result["memory_used_gb"] > 0

    @pytest.mark.asyncio
    async def test_metrics_timeout_returns_zeros(self):
        """Test that metrics endpoint returns zero values on timeout."""
        import asyncio

        import core.dashboard as dash

        fake_psutil = _make_psutil()
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            # Patch asyncio.gather to raise TimeoutError
            async def _timeout_gather(*args, **kwargs):
                # Close coroutines to avoid RuntimeWarning about unawaited to_thread calls
                for coro in args:
                    if hasattr(coro, 'close'):
                        coro.close()
                raise asyncio.TimeoutError("simulated timeout")

            with patch("asyncio.gather", side_effect=_timeout_gather):
                result = await dash.metrics()
            assert result["cpu_percent"] == 0
            assert result["memory_percent"] == 0


# ── Tests: timeout handlers ────────────────────────────────────────────────


class TestTimeoutHandlers:
    """Tests for timeout exception handlers in dashboard endpoints."""

    @pytest.mark.asyncio
    async def test_overview_timeout_returns_partial_data(self):
        """Test that dashboard_overview returns partial data on timeout."""
        import asyncio

        import core.dashboard as dash

        fake_psutil = _make_psutil()
        with patch.dict(sys.modules, {"psutil": fake_psutil}), \
             patch("subprocess.run", side_effect=FileNotFoundError("no nvidia")):
            # Patch asyncio.gather to raise TimeoutError
            async def _timeout_gather(*args, **kwargs):
                # Close coroutines to avoid RuntimeWarning about unawaited to_thread calls
                for coro in args:
                    if hasattr(coro, 'close'):
                        coro.close()
                raise asyncio.TimeoutError("simulated timeout")

            with patch("asyncio.gather", side_effect=_timeout_gather):
                result = await dash.dashboard_overview()
            assert result["cpu"]["percent"] == 0
            assert result["cpu"]["cores"] == 0
            assert result["memory"]["percent"] == 0
            assert result["memory"]["used_gb"] == 0
            assert result["memory"]["total_gb"] == 0
            assert result["disks"] == []
            assert result["gpus"] == []
            assert result["logs"]["total"] == 0
            assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_health_check_timeout_returns_healthy_status(self):
        """Test that health_check returns healthy status on timeout (zero values)."""
        import asyncio

        import core.dashboard as dash

        fake_psutil = _make_psutil()
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            # Patch asyncio.gather to raise TimeoutError
            async def _timeout_gather(*args, **kwargs):
                # Close coroutines to avoid RuntimeWarning about unawaited to_thread calls
                for coro in args:
                    if hasattr(coro, 'close'):
                        coro.close()
                raise asyncio.TimeoutError("simulated timeout")

            with patch("asyncio.gather", side_effect=_timeout_gather):
                result = await dash.health_check()
            # With zero CPU/memory, status should be "healthy"
            assert result["status"] == "healthy"
            assert result["issues"] == []
            assert "timestamp" in result
