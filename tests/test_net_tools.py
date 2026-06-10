"""Tests for core.net_tools — DNS lookup, ping, port scan, traceroute."""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import pytest

from core.net_tools import (
    _parse_ping_output,
    _parse_traceroute,
    dns_lookup,
    ping_host,
    port_open,
    scan_ports,
    traceroute,
)


# ── DNS lookup ────────────────────────────────────────────────────────────────

class TestDnsLookup:
    def test_a_record_localhost(self):
        result = dns_lookup("localhost", "A")
        assert result["type"] == "A"
        assert isinstance(result["addresses"], list)
        # localhost always resolves
        assert len(result["addresses"]) > 0

    def test_invalid_hostname_returns_error(self):
        result = dns_lookup("this.host.does.not.exist.invalid", "A")
        assert "error" in result
        assert result["addresses"] == []

    def test_ptr_record_loopback(self):
        result = dns_lookup("127.0.0.1", "PTR")
        assert result["type"] == "PTR"
        assert isinstance(result["addresses"], list)

    def test_aaaa_record(self):
        result = dns_lookup("localhost", "AAAA")
        assert result["type"] == "AAAA"
        assert isinstance(result["addresses"], list)

    def test_result_contains_hostname_field(self):
        result = dns_lookup("localhost")
        assert result["hostname"] == "localhost"

    def test_result_with_dnspython_fallback_for_mx(self):
        # dnspython may not be installed; should gracefully fall back
        result = dns_lookup("gmail.com", "MX")
        assert "type" in result
        assert "addresses" in result


# ── Ping output parsing ───────────────────────────────────────────────────────

class TestParsePingOutput:
    def test_windows_style_output(self):
        output = (
            "Pinging 8.8.8.8 with 32 bytes of data:\n"
            "Reply from 8.8.8.8: bytes=32 time=12ms TTL=118\n"
            "Ping statistics for 8.8.8.8:\n"
            "    Packets: Sent = 4, Received = 4, Lost = 0 (0% loss),\n"
            "Approximate round trip times in milli-seconds:\n"
            "    Minimum = 11ms, Maximum = 14ms, Average = 12ms\n"
        )
        result = _parse_ping_output("8.8.8.8", output, 4)
        assert result["success"] is True
        assert result["packets_received"] == 4
        assert result["avg_ms"] == 12.0

    def test_unix_style_output(self):
        output = (
            "PING 8.8.8.8 (8.8.8.8): 56 data bytes\n"
            "4 packets transmitted, 4 packets received, 0.0% packet loss\n"
            "round-trip min/avg/max/stddev = 10.5/12.3/14.1/1.4 ms\n"
        )
        result = _parse_ping_output("8.8.8.8", output, 4)
        assert result["success"] is True
        assert result["packets_received"] == 4
        assert result["avg_ms"] == 12.3

    def test_no_reply_returns_failure(self):
        output = (
            "Pinging 192.168.99.99 with 32 bytes of data:\n"
            "Request timed out.\n"
            "Packets: Sent = 4, Received = 0, Lost = 4 (100% loss),\n"
        )
        result = _parse_ping_output("192.168.99.99", output, 4)
        assert result["success"] is False
        assert result["packets_received"] == 0


# ── Port scan ─────────────────────────────────────────────────────────────────

class TestPortScan:
    def test_scan_loopback_ports(self):
        results = scan_ports("127.0.0.1", [9999, 19999], timeout=0.5)
        assert isinstance(results, dict)
        assert 9999 in results
        assert 19999 in results

    def test_port_open_false_for_unbound_port(self):
        # Port 9 (discard) is usually closed
        assert port_open("127.0.0.1", 65432, timeout=0.3) is False

    def test_scan_returns_correct_keys(self):
        results = scan_ports("127.0.0.1", [80, 443], timeout=0.3)
        assert set(results.keys()) == {80, 443}
        assert all(isinstance(v, bool) for v in results.values())


# ── Traceroute parsing ────────────────────────────────────────────────────────

class TestParseTraceroute:
    def test_windows_style(self):
        output = (
            "Tracing route to 8.8.8.8 over a maximum of 30 hops:\n"
            "  1     1 ms     1 ms     1 ms  192.168.1.1\n"
            "  2    10 ms     9 ms    10 ms  10.0.0.1\n"
            "Trace complete.\n"
        )
        hops = _parse_traceroute(output)
        assert len(hops) == 2
        assert hops[0]["hop"] == 1
        assert hops[0]["address"] == "192.168.1.1"

    def test_empty_output_returns_empty(self):
        assert _parse_traceroute("") == []


# ── Ping host integration (subprocess) ───────────────────────────────────────

class TestPingHost:
    def test_ping_localhost(self):
        result = ping_host("127.0.0.1", count=1, timeout=2)
        assert result["host"] == "127.0.0.1"
        assert "packets_sent" in result
        assert isinstance(result["success"], bool)

    def test_ping_nonexistent_host_returns_result_dict(self):
        result = ping_host("192.0.2.1", count=1, timeout=1)
        assert "success" in result
        assert "host" in result


# ── Action executor integration ───────────────────────────────────────────────

class TestNetActionsInExecutor:
    def test_dns_lookup_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "dns_lookup" in ActionExecutor._dispatch_table

    def test_ping_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "ping" in ActionExecutor._dispatch_table

    def test_port_scan_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "port_scan" in ActionExecutor._dispatch_table

    def test_dns_lookup_executor(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor()
        result = executor.execute_sync({"action": "dns_lookup", "hostname": "localhost"})
        assert "addresses" in result

    def test_ping_executor(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor()
        result = executor.execute_sync({"action": "ping", "host": "127.0.0.1", "count": 1})
        assert "success" in result

    def test_port_scan_executor(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor()
        result = executor.execute_sync({"action": "port_scan", "host": "127.0.0.1", "ports": [65432]})
        assert result["success"] is True
        assert "results" in result
