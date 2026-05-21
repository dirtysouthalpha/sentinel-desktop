"""Tests for core.dashboard — System Dashboard API."""

from __future__ import annotations

import importlib
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core import dashboard


# ─── Unit helpers ──────────────────────────────────────────────────────────

class TestGetCpuInfo:
    """Tests for _get_cpu_info."""

    @patch("core.dashboard.psutil", create=True)
    def test_returns_cpu_data_with_psutil(self, mock_psutil_mod):
        """When psutil is available, return percent, counts, and freq."""
        mock_psutil = MagicMock()
        mock_psutil.cpu_percent.return_value = 42.5
        mock_psutil.cpu_count.side_effect = [4, 8]
        mock_psutil.cpu_freq.return_value = MagicMock(current=3200.0)
        mock_psutil_mod.cpu_percent = mock_psutil.cpu_percent
        mock_psutil_mod.cpu_count = mock_psutil.cpu_count
        mock_psutil_mod.cpu_freq = mock_psutil.cpu_freq

        with patch.dict("sys.modules", {"psutil": mock_psutil_mod}):
            result = dashboard._get_cpu_info()

        assert result["percent"] == 42.5
        assert result["count_physical"] == 4
        assert result["count_logical"] == 8
        assert result["freq_current"] == 3200.0

    def test_returns_fallback_without_psutil(self):
        """When psutil is not importable, return a minimal fallback dict."""
        with patch.dict("sys.modules", {"psutil": None}):
            result = dashboard._get_cpu_info()

        assert "percent" in result
        assert result["percent"] == 0


class TestGetMemoryInfo:
    """Tests for _get_memory_info."""

    @patch("core.dashboard.psutil", create=True)
    def test_returns_memory_data_with_psutil(self, mock_psutil_mod):
        """Return total, used, available, and percent from psutil."""
        mem = MagicMock()
        mem.total = 16 * (1024**3)
        mem.used = 8 * (1024**3)
        mem.available = 8 * (1024**3)
        mem.percent = 50.0
        mock_psutil_mod.virtual_memory.return_value = mem

        with patch.dict("sys.modules", {"psutil": mock_psutil_mod}):
            result = dashboard._get_memory_info()

        assert result["total_gb"] == 16.0
        assert result["used_gb"] == 8.0
        assert result["available_gb"] == 8.0
        assert result["percent"] == 50.0

    def test_returns_fallback_without_psutil(self):
        """Fallback when psutil is unavailable."""
        with patch.dict("sys.modules", {"psutil": None}):
            result = dashboard._get_memory_info()

        assert "total_gb" in result
        assert result["total_gb"] == 0


class TestGetDiskInfo:
    """Tests for _get_disk_info."""

    @patch("core.dashboard.psutil", create=True)
    def test_returns_disk_list_with_psutil(self, mock_psutil_mod):
        """Return a list of disk partition info dicts."""
        partition = MagicMock()
        partition.mountpoint = "/"
        mock_psutil_mod.disk_partitions.return_value = [partition]

        usage = MagicMock()
        usage.total = 500 * (1024**3)
        usage.used = 250 * (1024**3)
        usage.free = 250 * (1024**3)
        usage.percent = 50.0
        mock_psutil_mod.disk_usage.return_value = usage

        with patch.dict("sys.modules", {"psutil": mock_psutil_mod}):
            result = dashboard._get_disk_info()

        assert len(result) == 1
        assert result[0]["mount"] == "/"
        assert result[0]["total_gb"] == 500.0
        assert result[0]["percent"] == 50.0

    @patch("core.dashboard.psutil", create=True)
    def test_skips_permission_denied_partitions(self, mock_psutil_mod):
        """Partitions that raise PermissionError should be silently skipped."""
        partition = MagicMock()
        partition.mountpoint = "/protected"
        mock_psutil_mod.disk_partitions.return_value = [partition]
        mock_psutil_mod.disk_usage.side_effect = PermissionError("nope")

        with patch.dict("sys.modules", {"psutil": mock_psutil_mod}):
            result = dashboard._get_disk_info()

        assert result == []

    def test_returns_empty_without_psutil(self):
        """Fallback when psutil is unavailable."""
        with patch.dict("sys.modules", {"psutil": None}):
            result = dashboard._get_disk_info()

        assert result == []


class TestGetGpuInfo:
    """Tests for _get_gpu_info."""

    def test_parses_nvidia_smi_output(self):
        """Parse nvidia-smi CSV output into GPU info dicts."""
        import subprocess
        with patch.object(subprocess, "run", return_value=MagicMock(
            returncode=0,
            stdout="RTX 4090, 8000, 24576, 65, 95, 250.5\n",
        )):
            result = dashboard._get_gpu_info()
        assert len(result) == 1
        assert result[0]["name"] == "RTX 4090"
        assert result[0]["temperature_c"] == 65.0

    def test_returns_empty_on_nvidia_smi_failure(self):
        """Return empty list if nvidia-smi exits non-zero."""
        import subprocess
        with patch.object(subprocess, "run", return_value=MagicMock(returncode=1, stdout="")):
            assert dashboard._get_gpu_info() == []

    def test_returns_empty_on_exception(self):
        """Return empty list if subprocess raises."""
        import subprocess
        with patch.object(subprocess, "run", side_effect=Exception("boom")):
            assert dashboard._get_gpu_info() == []


class TestCountLogEntries:
    """Tests for _count_log_entries."""

    def test_returns_zero_when_no_log_dir(self, tmp_path):
        """Return zero when log directory does not exist."""
        with patch.object(Path, "home", return_value=tmp_path):
            result = dashboard._count_log_entries()
        assert result["total_logs"] == 0

    def test_counts_json_files_in_log_dir(self, tmp_path):
        """Count .json files in the log directory."""
        log_dir = tmp_path / ".sentinel" / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "run1.json").write_text("{}")
        (log_dir / "run2.json").write_text("{}")
        (log_dir / "notes.txt").write_text("not a log")

        with patch.object(Path, "home", return_value=tmp_path):
            result = dashboard._count_log_entries()
        assert result["total_logs"] == 2


# ─── Endpoint tests ───────────────────────────────────────────────────────

class TestDashboardOverview:
    """Tests for the /dashboard/overview endpoint."""

    @pytest.mark.asyncio
    async def test_overview_returns_required_keys(self):
        """Overview response contains system, cpu, memory, disks, gpus, logs."""
        result = await dashboard.dashboard_overview()
        assert "system" in result
        assert "cpu" in result
        assert "memory" in result
        assert "disks" in result
        assert "gpus" in result
        assert "logs" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_overview_uptime_is_positive(self):
        """Uptime seconds should be >= 0."""
        result = await dashboard.dashboard_overview()
        assert result["system"]["uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_overview_platform_info(self):
        """Platform, hostname, and python version are populated."""
        result = await dashboard.dashboard_overview()
        sys_info = result["system"]
        assert sys_info["platform"]
        assert sys_info["hostname"]
        assert sys_info["python_version"]


class TestHealthCheck:
    """Tests for the /dashboard/health endpoint."""

    @pytest.mark.asyncio
    async def test_healthy_when_resources_normal(self):
        """Status is healthy when CPU and memory are under 90%."""
        with patch.object(dashboard, "_get_cpu_info", return_value={"percent": 30}), \
             patch.object(dashboard, "_get_memory_info", return_value={"percent": 40}):
            result = await dashboard.health_check()
        assert result["status"] == "healthy"
        assert result["issues"] == []

    @pytest.mark.asyncio
    async def test_warning_when_memory_high(self):
        """Status is warning when memory exceeds 90%."""
        with patch.object(dashboard, "_get_cpu_info", return_value={"percent": 30}), \
             patch.object(dashboard, "_get_memory_info", return_value={"percent": 95}):
            result = await dashboard.health_check()
        assert result["status"] == "warning"
        assert any("Memory" in i for i in result["issues"])

    @pytest.mark.asyncio
    async def test_warning_when_cpu_high(self):
        """Status is warning when CPU exceeds 90%."""
        with patch.object(dashboard, "_get_cpu_info", return_value={"percent": 99}), \
             patch.object(dashboard, "_get_memory_info", return_value={"percent": 30}):
            result = await dashboard.health_check()
        assert result["status"] == "warning"
        assert any("CPU" in i for i in result["issues"])

    @pytest.mark.asyncio
    async def test_health_check_appends_to_history(self):
        """Each health check call appends to _health_checks."""
        dashboard._health_checks.clear()
        with patch.object(dashboard, "_get_cpu_info", return_value={"percent": 10}), \
             patch.object(dashboard, "_get_memory_info", return_value={"percent": 20}):
            await dashboard.health_check()
            await dashboard.health_check()
        assert len(dashboard._health_checks) == 2

    @pytest.mark.asyncio
    async def test_health_check_trims_at_100(self):
        """_health_checks list is trimmed to last 50 when exceeding 100."""
        dashboard._health_checks.clear()
        dashboard._health_checks.extend([{"status": "healthy"}] * 100)
        with patch.object(dashboard, "_get_cpu_info", return_value={"percent": 10}), \
             patch.object(dashboard, "_get_memory_info", return_value={"percent": 20}):
            await dashboard.health_check()
        # 101 > 100 triggers trim: keep last 50 of original + 1 new = trimmed to last 50 total
        assert len(dashboard._health_checks) == 50


class TestMetrics:
    """Tests for the /dashboard/metrics endpoint."""

    @pytest.mark.asyncio
    async def test_metrics_returns_expected_keys(self):
        """Metrics endpoint returns cpu_percent, memory_percent, memory_used_gb."""
        result = await dashboard.metrics()
        assert "cpu_percent" in result
        assert "memory_percent" in result
        assert "memory_used_gb" in result
