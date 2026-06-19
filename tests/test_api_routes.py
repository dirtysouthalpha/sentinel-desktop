"""Tests for api.routes — the v18 route registry.

The hard invariant: the registry must record the exact v17 route set (62
method/path pairs), proving the migration from imperative ``_register_*_routes``
calls to the registry-driven approach introduced zero drift.
"""

from __future__ import annotations

import pytest

from api.routes import RouteRegistry, api_route, collect_routes
from api.server import SentinelServer
from config import Config


def _make_server() -> SentinelServer:
    return SentinelServer(Config())


# The exact 62 (METHOD, path) pairs the v17 _register_*_routes methods wired.
# Captured from the imperative app.get/post/put/delete/websocket calls.
_V17_BASELINE_ROUTES = frozenset(
    {
        ("POST", "/goal"),
        ("POST", "/command"),
        ("GET", "/screenshot"),
        ("GET", "/status"),
        ("GET", "/windows"),
        ("GET", "/processes"),
        ("GET", "/system"),
        ("GET", "/config"),
        ("PUT", "/config"),
        ("GET", "/log"),
        ("POST", "/stop"),
        ("GET", "/scripts"),
        ("POST", "/scripts/run"),
        ("POST", "/powershell"),
        ("POST", "/recorder/start"),
        ("POST", "/recorder/stop"),
        ("GET", "/workflows"),
        ("POST", "/workflows/run"),
        ("GET", "/schedule"),
        ("POST", "/schedule/add"),
        ("POST", "/schedule/remove"),
        ("POST", "/schedule/run"),
        ("POST", "/notify"),
        ("GET", "/plugins"),
        ("POST", "/plugins/reload"),
        ("GET", "/agents"),
        ("POST", "/agents/submit"),
        ("POST", "/agents/cancel"),
        ("GET", "/agents/{session_id}"),
        ("POST", "/auth/login"),
        ("POST", "/auth/logout"),
        ("GET", "/auth/users"),
        ("GET", "/audit/export"),
        ("GET", "/vault/keys"),
        ("GET", "/workflows/builder/list"),
        ("POST", "/workflows/builder/create"),
        ("GET", "/workflows/builder/templates"),
        ("POST", "/workflows/builder/{wf_id}/add-step"),
        ("POST", "/workflows/builder/{wf_id}/remove-step"),
        ("DELETE", "/workflows/builder/{wf_id}"),
        ("POST", "/workflows/builder/{wf_id}/duplicate"),
        ("WEBSOCKET", "/ws"),
        ("WEBSOCKET", "/ws/terminal"),
        ("GET", "/daemon/status"),
        ("POST", "/daemon/start"),
        ("POST", "/daemon/stop"),
        ("GET", "/fleet/nodes"),
        ("POST", "/fleet/register"),
        ("POST", "/fleet/unregister"),
        ("GET", "/jobs"),
        ("POST", "/jobs/submit"),
        ("GET", "/jobs/{job_id}"),
        ("POST", "/jobs/{job_id}/cancel"),
        ("GET", "/memory/facts"),
        ("GET", "/memory/facts/{key}"),
        ("POST", "/memory/facts"),
        ("DELETE", "/memory/facts/{key}"),
        ("GET", "/memory/search"),
        ("GET", "/memory/episodes"),
        ("GET", "/memory/episodes/search"),
        ("POST", "/conductor/run"),
        ("GET", "/"),
    }
)


# ---------------------------------------------------------------------------
# Parity: registry == v17 baseline
# ---------------------------------------------------------------------------
class TestRouteParity:
    def test_registry_records_all_62_routes(self):
        server = _make_server()
        server.create_app()
        assert len(server._route_registry) == 62

    def test_registry_pairs_equal_v17_baseline(self):
        """No route may be silently added or removed vs the v17 set."""
        server = _make_server()
        server.create_app()
        pairs = server._route_registry.method_path_pairs()
        assert pairs == _V17_BASELINE_ROUTES, (
            f"drift: added={pairs - _V17_BASELINE_ROUTES} removed={_V17_BASELINE_ROUTES - pairs}"
        )

    def test_registry_built_during_create_app(self):
        server = _make_server()
        assert not hasattr(server, "_route_registry") or len(server._route_registry) == 0
        server.create_app()
        assert len(server._route_registry) == 62

    def test_contains_check(self):
        server = _make_server()
        server.create_app()
        assert ("POST", "/goal") in server._route_registry
        assert ("GET", "/nonexistent") not in server._route_registry


# ---------------------------------------------------------------------------
# RouteRegistry primitives
# ---------------------------------------------------------------------------
class TestRouteRegistry:
    def test_add_records_route(self):
        reg = RouteRegistry()
        reg.add("GET", "/foo", lambda: None)
        assert len(reg) == 1
        assert ("GET", "/foo") in reg

    def test_add_ignores_duplicates(self):
        reg = RouteRegistry()
        reg.add("GET", "/foo", lambda: None)
        reg.add("GET", "/foo", lambda: None)
        assert len(reg) == 1

    def test_method_case_normalized(self):
        reg = RouteRegistry()
        reg.add("post", "/bar", lambda: None)
        assert ("POST", "/bar") in reg

    def test_add_decorated_pulls_marked_handlers(self):
        class Stub:
            @api_route("GET", "/decorated")
            async def _h1(self):
                pass

            @api_route("POST", "/also")
            async def _h2(self):
                pass

        stub = Stub()
        routes = collect_routes(stub)
        assert {("GET", "/decorated"), ("POST", "/also")} == {(m, p) for m, p, _ in routes}


# ---------------------------------------------------------------------------
# api_route decorator
# ---------------------------------------------------------------------------
class TestApiRouteDecorator:
    def test_marks_function_with_spec(self):
        @api_route("GET", "/x")
        async def handler(self):
            pass

        assert handler.__route_spec__.method == "GET"
        assert handler.__route_spec__.path == "/x"

    def test_returns_function_unchanged(self):
        import asyncio

        @api_route("POST", "/y")
        async def handler(self):
            return "kept"

        assert asyncio.new_event_loop().run_until_complete(handler(None)) == "kept"

    def test_rejects_unknown_method(self):
        with pytest.raises(ValueError):

            @api_route("FETCH", "/z")
            async def handler(self):
                pass

    def test_accepts_websocket(self):
        @api_route("websocket", "/ws")
        async def handler(self):
            pass

        assert handler.__route_spec__.method == "WEBSOCKET"
