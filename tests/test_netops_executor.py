"""Tests for netops action schemas and executor dispatch."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.action_schemas import ACTION_MODELS, validate_action


class TestSSHActionSchemas:
    def test_ssh_connect_valid(self):
        out, errs = validate_action(
            {
                "action": "ssh_connect",
                "hostname": "192.168.1.1",
                "username": "admin",
                "password": "secret",
            }
        )
        assert errs == []
        assert out["hostname"] == "192.168.1.1"
        assert out["port"] == 22  # default

    def test_ssh_connect_missing_hostname(self):
        _, errs = validate_action({"action": "ssh_connect"})
        assert errs

    def test_ssh_connect_invalid_port(self):
        _, errs = validate_action({"action": "ssh_connect", "hostname": "x", "port": 99999})
        assert errs

    def test_ssh_disconnect_valid(self):
        out, errs = validate_action({"action": "ssh_disconnect", "hostname": "192.168.1.1"})
        assert errs == []

    def test_ssh_run_valid(self):
        out, errs = validate_action(
            {
                "action": "ssh_run",
                "hostname": "192.168.1.1",
                "command": "show version",
            }
        )
        assert errs == []
        assert out["timeout"] == 30.0  # default

    def test_ssh_run_missing_command(self):
        _, errs = validate_action({"action": "ssh_run", "hostname": "x"})
        assert errs

    def test_ssh_show_valid(self):
        out, errs = validate_action(
            {
                "action": "ssh_show",
                "hostname": "192.168.1.1",
                "what": "interfaces",
            }
        )
        assert errs == []
        assert out["device_type"] == "generic"

    def test_ssh_show_invalid_what(self):
        _, errs = validate_action({"action": "ssh_show", "hostname": "x", "what": "explode"})
        assert errs

    def test_ssh_ping_valid(self):
        out, errs = validate_action(
            {
                "action": "ssh_ping",
                "hostname": "192.168.1.1",
                "target": "8.8.8.8",
            }
        )
        assert errs == []
        assert out["count"] == 4

    def test_ssh_ping_count_bounds(self):
        _, errs = validate_action(
            {
                "action": "ssh_ping",
                "hostname": "x",
                "target": "y",
                "count": 0,
            }
        )
        assert errs
        _, errs = validate_action(
            {
                "action": "ssh_ping",
                "hostname": "x",
                "target": "y",
                "count": 200,
            }
        )
        assert errs


@pytest.mark.parametrize(
    "name", ["ssh_connect", "ssh_disconnect", "ssh_run", "ssh_show", "ssh_ping"]
)
def test_netops_actions_are_modeled(name):
    assert name in ACTION_MODELS


class TestExecutorSSHDispatch:
    """Test that SSH actions dispatch through the executor."""

    def _make_executor(self):
        from core.action_executor import ActionExecutor

        return ActionExecutor()

    def test_ssh_connect_dispatches(self):
        with (
            patch("core.netops.ssh_client._HAS_PARAMIKO", True),
            patch("core.netops.ssh_client.paramiko"),
        ):
            executor = self._make_executor()
            result = executor.execute_sync(
                {
                    "action": "ssh_connect",
                    "hostname": "192.168.1.1",
                    "username": "admin",
                    "password": "secret",
                }
            )
            assert result["success"] is True
            assert "192.168.1.1" in result["output"]

    def test_ssh_disconnect_not_connected(self):
        executor = self._make_executor()
        result = executor.execute_sync(
            {
                "action": "ssh_disconnect",
                "hostname": "192.168.1.1",
            }
        )
        assert result["success"] is False

    def test_ssh_run_not_connected(self):
        executor = self._make_executor()
        result = executor.execute_sync(
            {
                "action": "ssh_run",
                "hostname": "10.0.0.1",
                "command": "show version",
            }
        )
        assert result["success"] is False
        assert "Not connected" in result["output"]

    def test_ssh_show_not_connected(self):
        executor = self._make_executor()
        result = executor.execute_sync(
            {
                "action": "ssh_show",
                "hostname": "10.0.0.1",
                "what": "version",
            }
        )
        assert result["success"] is False

    def test_ssh_ping_not_connected(self):
        executor = self._make_executor()
        result = executor.execute_sync(
            {
                "action": "ssh_ping",
                "hostname": "10.0.0.1",
                "target": "8.8.8.8",
            }
        )
        assert result["success"] is False
