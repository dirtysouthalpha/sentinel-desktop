"""Gap tests for core/netops/output_parser.py — lines 42-43, 125."""

from __future__ import annotations

from core.netops.output_parser import parse_interfaces, parse_ping


class TestParseInterfacesShortLines:
    """Lines 42-43: elif len(parts) >= 2 branch for lines with 2-5 words."""

    def test_two_part_line_parsed_as_interface(self) -> None:
        output = "eth0 192.168.1.1"
        result = parse_interfaces(output)
        assert len(result) == 1
        assert result[0]["interface"] == "eth0"
        assert result[0]["ip_address"] == "192.168.1.1"
        assert result[0]["status"] == "unknown"
        assert result[0]["protocol"] == "unknown"

    def test_four_part_line_parsed_as_interface(self) -> None:
        # 4 parts — falls in the 2-5 range (not >=6)
        output = "Gi0/0 10.0.0.1 up up"
        result = parse_interfaces(output)
        assert len(result) == 1
        assert result[0]["interface"] == "Gi0/0"
        assert result[0]["ip_address"] == "10.0.0.1"


class TestParsePingWindowsReplyFrom:
    """Line 125: 'Reply from' in Windows ping output sets success=True."""

    def test_windows_ping_reply_from_success(self) -> None:
        output = (
            "Pinging 8.8.8.8 with 32 bytes of data:\n"
            "Reply from 8.8.8.8: bytes=32 time=5ms TTL=118\n"
            "Reply from 8.8.8.8: bytes=32 time=6ms TTL=118\n"
        )
        result = parse_ping(output)
        assert result["success"] is True

    def test_lowercase_reply_from_success(self) -> None:
        output = "reply from 192.168.1.1: icmp_seq=1 ttl=64 time=1.2 ms\n"
        result = parse_ping(output)
        assert result["success"] is True
