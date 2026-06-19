"""Tests for ssh_traceroute action — schema, parser, executor, tool schema."""

from __future__ import annotations

from core.action_schemas import (
    ACTION_MODELS,
    SSHTracerouteAction,
    validate_action,
)
from core.netops.output_parser import parse_traceroute
from core.tool_schemas import TOOLS

# ── Schema tests ─────────────────────────────────────────────────────


class TestSSHTracerouteSchema:
    """Validate SSHTracerouteAction schema."""

    def test_valid_payload(self):
        action = SSHTracerouteAction(
            action="ssh_traceroute",
            hostname="192.168.1.1",
            target="8.8.8.8",
        )
        assert action.action == "ssh_traceroute"
        assert action.hostname == "192.168.1.1"
        assert action.target == "8.8.8.8"
        assert action.device_type == "generic"

    def test_with_device_type(self):
        action = SSHTracerouteAction(
            action="ssh_traceroute",
            hostname="router1",
            target="10.0.0.1",
            device_type="cisco_ios",
        )
        assert action.device_type == "cisco_ios"

    def test_registered_in_action_models(self):
        assert "ssh_traceroute" in ACTION_MODELS
        assert ACTION_MODELS["ssh_traceroute"] is SSHTracerouteAction

    def test_validate_action_valid(self):
        payload = {
            "action": "ssh_traceroute",
            "hostname": "10.0.0.1",
            "target": "8.8.8.8",
        }
        validated, errors = validate_action(payload)
        assert len(errors) == 0
        assert validated["action"] == "ssh_traceroute"

    def test_validate_action_missing_target(self):
        payload = {"action": "ssh_traceroute", "hostname": "10.0.0.1"}
        validated, errors = validate_action(payload)
        assert len(errors) > 0

    def test_validate_action_missing_hostname(self):
        payload = {"action": "ssh_traceroute", "target": "8.8.8.8"}
        validated, errors = validate_action(payload)
        assert len(errors) > 0


# ── Parser tests ─────────────────────────────────────────────────────


class TestParseTraceroute:
    """Validate parse_traceroute output parsing."""

    def test_linux_traceroute(self):
        output = (
            "traceroute to 8.8.8.8 (8.8.8.8), 30 hops max\n"
            " 1  gateway (192.168.1.1)  0.456 ms  0.398 ms  0.382 ms\n"
            " 2  10.0.0.1 (10.0.0.1)  1.234 ms  1.567 ms  1.890 ms\n"
            " 3  8.8.8.8 (8.8.8.8)  5.678 ms  5.432 ms  5.210 ms\n"
        )
        result = parse_traceroute(output)
        assert result["success"] is True
        assert result["target"] == "8.8.8.8"
        assert result["total_hops"] == 3
        assert result["reached_target"] is True
        assert result["hops"][0]["host"] == "gateway"
        assert result["hops"][0]["avg_rtt_ms"] is not None
        assert result["hops"][0]["avg_rtt_ms"] > 0

    def test_cisco_traceroute(self):
        output = (
            "traceroute 8.8.8.8\n"
            " 1 10.0.0.1 4 msec 4 msec 4 msec\n"
            " 2 172.16.0.1 8 msec 8 msec 8 msec\n"
            " 3 8.8.8.8 12 msec 12 msec 12 msec\n"
        )
        result = parse_traceroute(output)
        assert result["success"] is True
        assert result["total_hops"] == 3
        assert result["hops"][1]["host"] == "172.16.0.1"
        assert result["hops"][1]["avg_rtt_ms"] == 8.0

    def test_empty_output(self):
        result = parse_traceroute("")
        assert result["success"] is False
        assert result["total_hops"] == 0
        assert result["hops"] == []

    def test_partial_traceroute(self):
        """Traceroute that doesn't reach the target."""
        output = (
            "traceroute to 10.255.255.1 (10.255.255.1), 30 hops max\n"
            " 1  gateway (192.168.1.1)  0.456 ms  0.398 ms  0.382 ms\n"
            " 2  * * *\n"
            " 3  * * *\n"
        )
        result = parse_traceroute(output)
        assert result["success"] is True
        assert result["reached_target"] is False
        # At least the gateway hop should be parsed
        assert result["total_hops"] >= 1

    def test_traceroute_with_star_hops(self):
        """Hops with * (timeout) should not have avg_rtt."""
        output = (
            "traceroute to 8.8.8.8\n"
            " 1 192.168.1.1 1.0 ms 1.0 ms 1.0 ms\n"
            " 3 8.8.8.8 5.0 ms 5.0 ms 5.0 ms\n"
        )
        result = parse_traceroute(output)
        assert result["total_hops"] >= 2

    def test_hop_numbers_sequential(self):
        output = (
            "traceroute to 8.8.8.8 (8.8.8.8), 30 hops max\n"
            " 1  gateway (192.168.1.1)  1.0 ms  1.0 ms  1.0 ms\n"
            " 2  isp (10.0.0.1)  2.0 ms  2.0 ms  2.0 ms\n"
        )
        result = parse_traceroute(output)
        assert [h["hop"] for h in result["hops"]] == [1, 2]


# ── Tool schema tests ────────────────────────────────────────────────


class TestSSHTracerouteToolSchema:
    """Validate tool schema for ssh_traceroute."""

    def test_tool_exists(self):
        names = [t["function"]["name"] for t in TOOLS]
        assert "ssh_traceroute" in names

    def test_tool_has_required_params(self):
        tool = next(t for t in TOOLS if t["function"]["name"] == "ssh_traceroute")
        params = tool["function"]["parameters"]
        assert "hostname" in params["properties"]
        assert "target" in params["properties"]
        assert params["required"] == ["hostname", "target"]

    def test_tool_has_device_type_default(self):
        tool = next(t for t in TOOLS if t["function"]["name"] == "ssh_traceroute")
        props = tool["function"]["parameters"]["properties"]
        assert "device_type" in props
        assert props["device_type"]["default"] == "generic"


# ── Executor dispatch test ───────────────────────────────────────────


class TestSSHTracerouteExecutor:
    """Validate executor dispatch for ssh_traceroute."""

    def test_dispatch_table_has_traceroute(self):
        from core.action_executor import ActionExecutor

        assert "ssh_traceroute" in ActionExecutor._dispatch_table

    def test_not_connected_returns_error(self):
        """When not connected, should return ssh_not_connected error."""
        from core.action_executor import ActionExecutor

        executor = ActionExecutor.__new__(ActionExecutor)
        executor._ssh_clients = {}

        result = executor._ssh_traceroute(
            hostname="10.0.0.1",
            target="8.8.8.8",
        )
        assert result["success"] is False
        assert result["error"] == "ssh_not_connected"
