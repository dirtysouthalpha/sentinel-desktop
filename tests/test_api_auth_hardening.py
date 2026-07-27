"""Regression tests for the v31 API-server hardening.

Covers:

* ~30 handlers (marketplace/install, sandbox, swarm, fleet, memory, vision,
  voice, playbooks, telemetry, workflow-generate) that did not call
  ``_check_auth`` at all and did not even accept an ``authorization``
  parameter, so setting ``SENTINEL_API_TOKEN`` protected ``/goal`` and
  ``/powershell`` but left plugin installation, agent spawning and fleet
  deployment wide open.
* ``_check_auth`` comparing the bearer token with ``!=`` instead of
  ``hmac.compare_digest``.
* Binding a non-loopback interface with authentication disabled.
* Path traversal through the ``name`` field of ``POST /recorder/stop``.
"""

from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

import api.server as mod
from config import Config

TOKEN = "s3cret-token"


@pytest.fixture
def server():
    return mod.SentinelServer(Config())


# ---------------------------------------------------------------------------
# Every previously-open endpoint now refuses unauthenticated calls
# ---------------------------------------------------------------------------

# Handlers that were unauthenticated before v31, with a kwargs set that reaches
# _check_auth without needing a live engine/subsystem.
PREVIOUSLY_OPEN_HANDLERS = [
    ("_handle_marketplace_list", {}),
    ("_handle_marketplace_install", {"req": None}),
    ("_handle_marketplace_uninstall", {"name": "x"}),
    ("_handle_sandbox_status", {}),
    ("_handle_sandbox_kill", {"name": "x"}),
    ("_handle_swarm_create", {"req": None}),
    ("_handle_swarm_assign", {"swarm_id": "s", "req": None}),
    ("_handle_swarm_status", {"swarm_id": "s"}),
    ("_handle_swarm_stop", {"swarm_id": "s"}),
    ("_handle_swarm_list", {}),
    ("_handle_memory_search", {"q": "hi"}),
    ("_handle_memory_stats", {}),
    ("_handle_vision_analyze", {"req": None}),
    ("_handle_fleet_nodes", {}),
    ("_handle_fleet_deploy", {"req": None}),
    ("_handle_fleet_health", {}),
    ("_handle_fleet_events", {}),
    ("_handle_playbooks_list", {}),
    ("_handle_playbooks_stats", {}),
    ("_handle_playbooks_learn", {}),
    ("_handle_workflow_generate", {"req": None}),
    ("_handle_voice_status", {}),
    ("_handle_voice_speak", {"req": None}),
    ("_handle_telemetry_summary", {}),
    ("_handle_telemetry_runs", {}),
    ("_handle_update_check", {}),
]


@pytest.mark.parametrize("handler_name,kwargs", PREVIOUSLY_OPEN_HANDLERS)
def test_handler_accepts_an_authorization_argument(server, handler_name, kwargs):
    """Pre-v31 these handlers had no ``authorization`` parameter at all."""
    handler = getattr(server, handler_name)
    params = inspect.signature(handler).parameters
    assert "authorization" in params, f"{handler_name} cannot receive a bearer token"


@pytest.mark.parametrize("handler_name,kwargs", PREVIOUSLY_OPEN_HANDLERS)
@pytest.mark.asyncio
async def test_unauthenticated_call_is_refused(server, handler_name, kwargs, monkeypatch):
    """With a token configured, an anonymous call must raise 401."""
    monkeypatch.setenv(mod.API_TOKEN_ENV, TOKEN)
    handler = getattr(server, handler_name)
    with pytest.raises(HTTPException) as exc:
        await handler(authorization=None, **kwargs)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("handler_name,kwargs", PREVIOUSLY_OPEN_HANDLERS)
@pytest.mark.asyncio
async def test_wrong_token_is_refused(server, handler_name, kwargs, monkeypatch):
    monkeypatch.setenv(mod.API_TOKEN_ENV, TOKEN)
    handler = getattr(server, handler_name)
    with pytest.raises(HTTPException) as exc:
        await handler(authorization="Bearer not-the-token", **kwargs)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_marketplace_install_does_not_install_when_unauthenticated(server, monkeypatch):
    """The auth check must run before any install work happens."""
    monkeypatch.setenv(mod.API_TOKEN_ENV, TOKEN)
    called = []
    import core.marketplace as marketplace

    monkeypatch.setattr(
        marketplace, "install_plugin", lambda name: called.append(name) or {"success": True}
    )
    with pytest.raises(HTTPException) as exc:
        await server._handle_marketplace_install(req=None, authorization=None)
    assert exc.value.status_code == 401
    assert called == [], "install_plugin ran for an unauthenticated caller"


@pytest.mark.asyncio
async def test_fleet_deploy_does_not_deploy_when_unauthenticated(server, monkeypatch):
    monkeypatch.setenv(mod.API_TOKEN_ENV, TOKEN)
    import core.fleet.redis_bus as redis_bus

    def _boom():
        raise AssertionError("get_fleet() reached without authentication")

    monkeypatch.setattr(redis_bus, "get_fleet", _boom)
    with pytest.raises(HTTPException) as exc:
        await server._handle_fleet_deploy(req=None, authorization=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_health_stays_open(server, monkeypatch):
    """/health is deliberately unauthenticated for load balancers."""
    monkeypatch.setenv(mod.API_TOKEN_ENV, TOKEN)
    result = await server._handle_health()
    assert "status" in result


# ---------------------------------------------------------------------------
# Constant-time token comparison
# ---------------------------------------------------------------------------


def test_check_auth_uses_constant_time_compare(server, monkeypatch):
    """The bearer comparison must go through hmac.compare_digest."""
    monkeypatch.setenv(mod.API_TOKEN_ENV, TOKEN)
    calls = []
    real = mod.hmac.compare_digest

    def _spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(mod.hmac, "compare_digest", _spy)
    server._check_auth(f"Bearer {TOKEN}")
    assert calls, "_check_auth did not use hmac.compare_digest"


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "Bearer ",
        f"Bearer {TOKEN}x",
        f"Bearer {TOKEN[:-1]}",
        TOKEN,
        f"bearer {TOKEN}",
        f"Basic {TOKEN}",
    ],
)
def test_check_auth_rejects_bad_headers(server, monkeypatch, header):
    monkeypatch.setenv(mod.API_TOKEN_ENV, TOKEN)
    with pytest.raises(HTTPException) as exc:
        server._check_auth(header)
    assert exc.value.status_code == 401


def test_check_auth_accepts_the_right_token(server, monkeypatch):
    monkeypatch.setenv(mod.API_TOKEN_ENV, TOKEN)
    server._check_auth(f"Bearer {TOKEN}")  # must not raise


# ---------------------------------------------------------------------------
# Insecure bind guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "100.70.240.55", "*", "example.com"])
def test_non_loopback_bind_without_token_is_refused(monkeypatch, host):
    monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)
    monkeypatch.delenv(mod.ALLOW_INSECURE_BIND_ENV, raising=False)
    with pytest.raises(mod.InsecureBindError):
        mod.require_secure_bind(host)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.5", ""])
def test_loopback_bind_without_token_is_allowed(monkeypatch, host):
    monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)
    monkeypatch.delenv(mod.ALLOW_INSECURE_BIND_ENV, raising=False)
    mod.require_secure_bind(host)  # must not raise


def test_non_loopback_bind_with_token_is_allowed(monkeypatch):
    monkeypatch.setenv(mod.API_TOKEN_ENV, TOKEN)
    monkeypatch.delenv(mod.ALLOW_INSECURE_BIND_ENV, raising=False)
    mod.require_secure_bind("0.0.0.0")  # must not raise


@pytest.mark.parametrize("flag", ["1", "true", "yes", "TRUE"])
def test_explicit_opt_out_allows_insecure_bind(monkeypatch, flag):
    monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)
    monkeypatch.setenv(mod.ALLOW_INSECURE_BIND_ENV, flag)
    mod.require_secure_bind("0.0.0.0")  # must not raise


@pytest.mark.parametrize("flag", ["0", "false", "no", "", "maybe"])
def test_non_affirmative_opt_out_still_refuses(monkeypatch, flag):
    monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)
    monkeypatch.setenv(mod.ALLOW_INSECURE_BIND_ENV, flag)
    with pytest.raises(mod.InsecureBindError):
        mod.require_secure_bind("0.0.0.0")


# ---------------------------------------------------------------------------
# /recorder/stop path traversal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "evil_name",
    [
        "../../core/engine",
        "..\\..\\core\\engine",
        "../../../Windows/System32/x",
        "/etc/passwd",
        "C:\\Windows\\system32\\evil",
        "sub/dir/name",
        "..",
        "....//....//x",
        "a\x00b",
    ],
)
def test_safe_script_stem_neutralises_traversal(evil_name):
    stem = mod._safe_script_stem(evil_name)
    for token in ("..", "/", "\\", ":", "\x00"):
        assert token not in stem, f"{token!r} survived sanitisation of {evil_name!r}"
    assert stem == stem.strip("._-")
    assert stem  # never empty


def test_safe_script_stem_keeps_reasonable_names():
    assert mod._safe_script_stem("My Script 2") == "my_script_2"
    assert mod._safe_script_stem("login-flow") == "login-flow"
    assert mod._safe_script_stem("with_underscore") == "with_underscore"


def test_safe_script_stem_defaults_when_nothing_survives():
    assert mod._safe_script_stem("...") == "untitled"
    assert mod._safe_script_stem("") == "untitled"
    assert mod._safe_script_stem("/") == "untitled"


@pytest.mark.asyncio
async def test_recorder_stop_writes_inside_scripts_dir(server, tmp_path, monkeypatch):
    """A traversal name must not escape the scripts/ directory on save."""
    import os

    saved: dict = {}

    class _Script:
        name = ""
        description = ""
        steps: list = []

        def save(self, path):
            saved["path"] = path

    class _Recorder:
        @staticmethod
        def stop_recording():
            return _Script()

    class _Engine:
        recorder = _Recorder()

    server.engine = _Engine()
    monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)

    req = mod.RecorderStopRequest(name="../../../pwned", description="")
    result = await server._handle_recorder_stop(req, authorization=None)

    assert result["status"] == "saved"
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(mod.__file__)), "scripts")
    written = os.path.normpath(saved["path"])
    assert os.path.dirname(written) == os.path.normpath(scripts_dir)
    assert "pwned.json" not in os.path.basename(os.path.dirname(written))
