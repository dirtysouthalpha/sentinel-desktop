"""Regression: ``_authenticate_ws`` token comparison + behaviour contract.

``_authenticate_ws`` (the main ``/ws`` agent-WebSocket auth handshake) used
to compare the presented token with ``!=``, while every other token check in
the API (``_check_auth``, ``/ws/terminal``) uses ``hmac.compare_digest`` —
so the most powerful endpoint (full agent control) had the weakest
comparison. The fix routes through ``hmac.compare_digest`` with a ``str()``
coercion so a non-string token (e.g. malformed JSON) still mismatches
instead of raising ``TypeError``.

Constant-time-ness itself is not unit-testable, so these tests instead lock
in the accept/reject behaviour contract for the main ``/ws`` handshake
(previously untested — only ``/ws/terminal`` had coverage) and guard the
``str()`` coercion against a future regression that drops it.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import api.server as mod
from config import Config

_TOKEN = "super-secret-ws-token"


def _make_server():
    return mod.SentinelServer(Config())


def _fake_ws(auth_payload: dict) -> MagicMock:
    """Build a MagicMock WebSocket whose ``receive_text`` yields *auth_payload*
    serialized to JSON."""
    ws = MagicMock()
    ws.receive_text = AsyncMock(return_value=json.dumps(auth_payload))
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestAuthenticateWs:
    def test_rejects_wrong_token_when_configured(self, monkeypatch):
        monkeypatch.setenv(mod.API_TOKEN_ENV, _TOKEN)
        server = _make_server()
        ws = _fake_ws({"token": "wrong"})
        assert asyncio.run(server._authenticate_ws(ws)) is False
        ws.close.assert_called_once()
        assert ws.send_json.call_args[0][0]["type"] == "auth_error"

    def test_accepts_correct_token_when_configured(self, monkeypatch):
        monkeypatch.setenv(mod.API_TOKEN_ENV, _TOKEN)
        server = _make_server()
        ws = _fake_ws({"token": _TOKEN})
        assert asyncio.run(server._authenticate_ws(ws)) is True
        ws.close.assert_not_called()

    def test_accepts_any_token_when_not_configured(self, monkeypatch):
        monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)
        server = _make_server()
        ws = _fake_ws({"token": "anything"})
        assert asyncio.run(server._authenticate_ws(ws)) is True

    def test_rejects_missing_token_key_when_configured(self, monkeypatch):
        monkeypatch.setenv(mod.API_TOKEN_ENV, _TOKEN)
        server = _make_server()
        ws = _fake_ws({})  # no "token" key -> default ""
        assert asyncio.run(server._authenticate_ws(ws)) is False

    def test_non_string_token_does_not_crash(self, monkeypatch):
        """A non-string token (malformed JSON) must mismatch and reject, not
        raise ``TypeError`` from ``compare_digest`` — the ``str()`` coercion
        preserves the pre-fix behaviour."""
        monkeypatch.setenv(mod.API_TOKEN_ENV, _TOKEN)
        server = _make_server()
        ws = _fake_ws({"token": 12345})  # int, not str
        assert asyncio.run(server._authenticate_ws(ws)) is False
        ws.close.assert_called_once()

    def test_timeout_closes_connection(self, monkeypatch):
        monkeypatch.setenv(mod.API_TOKEN_ENV, _TOKEN)
        server = _make_server()
        ws = MagicMock()
        ws.receive_text = AsyncMock(side_effect=asyncio.TimeoutError)
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        assert asyncio.run(server._authenticate_ws(ws)) is False
        ws.close.assert_called_once()

    def test_invalid_json_closes_connection(self, monkeypatch):
        monkeypatch.setenv(mod.API_TOKEN_ENV, _TOKEN)
        server = _make_server()
        ws = MagicMock()
        ws.receive_text = AsyncMock(return_value="not json")
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        assert asyncio.run(server._authenticate_ws(ws)) is False
        ws.close.assert_called_once()
