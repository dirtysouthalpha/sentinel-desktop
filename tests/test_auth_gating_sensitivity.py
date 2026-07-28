"""Authentication must track how sensitive an endpoint actually is.

v31 gated ~66 handlers but the result was inverted in one place: `/status`
(agent-loop liveness - `{"running": false, "step": 0, ...}`) required a token
and broke fleet monitoring across the Tailscale mesh, while
`/dashboard/overview` - hostname, OS and Python versions, CPU model, RAM, GPU
list and every disk mount with its size - was reachable with no token at all,
because `core.dashboard` is mounted via `include_router` and never passes
through `APIServer._check_auth`.

These tests pin the intended contract so the inversion cannot return.
"""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dashboard import API_TOKEN_ENV, router as dashboard_router

TOKEN = "unit-test-token-value"

# Endpoints that must keep working WITHOUT credentials: liveness/monitoring
# signals the fleet polls. Each returns only coarse state.
OPEN_DASHBOARD_ROUTES = ["/dashboard/health", "/dashboard/metrics"]
# Endpoints that expose host reconnaissance and must require a token.
GATED_DASHBOARD_ROUTES = ["/dashboard/overview"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(API_TOKEN_ENV, TOKEN)
    app = FastAPI()
    app.include_router(dashboard_router)
    return TestClient(app)


@pytest.fixture
def client_no_token(monkeypatch):
    monkeypatch.delenv(API_TOKEN_ENV, raising=False)
    app = FastAPI()
    app.include_router(dashboard_router)
    return TestClient(app)


@pytest.mark.parametrize("route", GATED_DASHBOARD_ROUTES)
def test_recon_route_requires_a_token(client, route):
    assert client.get(route).status_code == 401


@pytest.mark.parametrize("route", GATED_DASHBOARD_ROUTES)
def test_recon_route_accepts_the_correct_token(client, route):
    r = client.get(route, headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200


@pytest.mark.parametrize("route", GATED_DASHBOARD_ROUTES)
def test_recon_route_rejects_a_wrong_token(client, route):
    r = client.get(route, headers={"Authorization": "Bearer not-the-token"})
    assert r.status_code == 401


@pytest.mark.parametrize("route", OPEN_DASHBOARD_ROUTES)
def test_liveness_routes_stay_open(client, route):
    """Monitors must not need credentials for a coarse liveness signal."""
    assert client.get(route).status_code == 200


def test_overview_actually_contains_recon_data(client):
    """Justifies gating it: if this ever stops leaking host detail, revisit."""
    body = client.get(
        "/dashboard/overview", headers={"Authorization": f"Bearer {TOKEN}"}
    ).json()
    assert "hostname" in body["system"]
    assert "platform" in body["system"]
    assert "disks" in body


def test_open_routes_do_not_leak_host_identity(client):
    """The endpoints we leave open must stay coarse."""
    for route in OPEN_DASHBOARD_ROUTES:
        body = client.get(route).json()
        flat = str(body).lower()
        assert os.environ.get("COMPUTERNAME", "\x00unlikely\x00").lower() not in flat
        assert "disks" not in body
        assert "hostname" not in str(body)


def test_gating_is_a_no_op_when_no_token_is_configured(client_no_token):
    """A purely local install with no token set keeps working."""
    for route in GATED_DASHBOARD_ROUTES + OPEN_DASHBOARD_ROUTES:
        assert client_no_token.get(route).status_code == 200


def test_status_handler_is_not_gated():
    """`/status` is agent-loop liveness; gating it broke fleet monitoring.

    Asserted structurally against the source so a future edit that reintroduces
    `self._check_auth(authorization)` into this handler fails here.
    """
    import ast
    import inspect
    import textwrap

    import api.server as srv

    # dedent: getsource on a method keeps its class indentation, which ast rejects.
    src = textwrap.dedent(inspect.getsource(srv.SentinelServer._handle_status))
    tree = ast.parse(src)
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "_check_auth"
    ]
    assert not calls, "/status must stay unauthenticated (see fleet monitoring)"
