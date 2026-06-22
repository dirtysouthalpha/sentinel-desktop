"""Regression: the mounted /dashboard router must require auth.

The ``/dashboard`` router (``core/dashboard.py``) is wired via
``app.include_router``, separately from the per-handler ``self._route()``
registrations. A prior auth sweep closed ``_check_auth`` gaps on the
daemon/fleet/jobs/memory/conductor handlers but missed this
separately-mounted router, so ``/dashboard/overview`` (host fingerprint:
hostname/platform/disks/GPU), ``/dashboard/metrics``, and
``/dashboard/chat/sentinel-ai`` (an unauthenticated proxy to the local
Ollama LLM on :11434) accepted unauthenticated requests even when
``SENTINEL_API_TOKEN`` was configured — an auth bypass under the v19
Fortress layer.

Fix: ``app.include_router(dashboard_router, dependencies=[Depends(
self._dashboard_auth_guard)])`` exempts the intentionally-public
``/dashboard/health`` liveness probe and routes every other dashboard route
through ``_check_auth``.

These tests go through the HTTP layer (TestClient) because the auth gate is
a router-level dependency, not handler-internal — direct handler calls
(e.g. ``await dash.dashboard_overview()``) would not exercise it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.server as mod
from config import Config

_TOKEN = "super-secret-dashboard-token"


def _client() -> TestClient:
    server = mod.SentinelServer(Config())
    return TestClient(server.create_app())


@pytest.fixture
def with_token(monkeypatch):
    monkeypatch.setenv(mod.API_TOKEN_ENV, _TOKEN)
    yield


@pytest.fixture
def fast_dashboard(monkeypatch):
    """Stub the dashboard's I/O helpers so handler-exercising tests are fast
    and host-independent — real disk/GPU enumeration can flirt with the
    endpoint's own 10s timeout on loaded or snap/btrfs-heavy hosts."""
    import core.dashboard as dash

    monkeypatch.setattr(dash, "_get_cpu_info", lambda: {"percent": 10.0, "count_logical": 4})
    monkeypatch.setattr(
        dash,
        "_get_memory_info",
        lambda: {"percent": 20.0, "used_gb": 4.0, "total_gb": 16.0, "available_gb": 12.0},
    )
    monkeypatch.setattr(
        dash,
        "_get_disk_info",
        lambda: [{"mount": "/", "percent": 30.0, "total_gb": 100.0, "used_gb": 30.0, "free_gb": 70.0}],
    )
    monkeypatch.setattr(dash, "_get_gpu_info", lambda: [])
    monkeypatch.setattr(dash, "_count_log_entries", lambda: {"total_logs": 0})
    yield


class TestDashboardRouterRequiresAuth:
    """With ``SENTINEL_API_TOKEN`` configured, sensitive dashboard routes 401
    without a bearer token."""

    def test_overview_requires_auth(self, with_token):
        with _client() as client:
            resp = client.get("/dashboard/overview")
        assert resp.status_code == 401

    def test_metrics_requires_auth(self, with_token):
        with _client() as client:
            resp = client.get("/dashboard/metrics")
        assert resp.status_code == 401

    def test_chat_requires_auth(self, with_token):
        with _client() as client:
            resp = client.post("/dashboard/chat/sentinel-ai", json={"message": "hi"})
        assert resp.status_code == 401

    def test_health_stays_public(self, with_token, fast_dashboard):
        """Regression guard: /dashboard/health is an intentionally public
        liveness probe and must NOT be gated, even with a token configured."""
        with _client() as client:
            resp = client.get("/dashboard/health")
        assert resp.status_code == 200
        assert resp.json()["status"] in {"healthy", "warning"}

    def test_overview_accepts_correct_bearer(self, with_token, fast_dashboard):
        """With the correct bearer token, _check_auth passes and overview
        returns 200 with the (stubbed) system data."""
        with _client() as client:
            resp = client.get(
                "/dashboard/overview", headers={"Authorization": f"Bearer {_TOKEN}"}
            )
        assert resp.status_code == 200
        assert "timestamp" in resp.json()


class TestDashboardRouterOpenInLocalhostMode:
    """With no ``SENTINEL_API_TOKEN`` configured (legacy localhost mode), the
    dashboard routes remain open — preserving existing local-automation UX."""

    def test_overview_open_without_token_configured(self, monkeypatch, fast_dashboard):
        monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)
        with _client() as client:
            resp = client.get("/dashboard/overview")
        assert resp.status_code == 200
