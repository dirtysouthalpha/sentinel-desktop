"""Tests for core.netops.output_parser — network output parsing."""

from __future__ import annotations

from core.netops.output_parser import (
    extract_ips,
    extract_macs,
    parse_arp_table,
    parse_interfaces,
    parse_ping,
    parse_routing_table,
    parse_version,
)


class TestParseInterfaces:
    def test_cisco_ios_format(self):
        output = """
Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0     192.168.1.1     YES NVRAM  up                    up
GigabitEthernet0/1     10.0.0.1        YES NVRAM  up                    up
GigabitEthernet0/2     unassigned      YES NVRAM  administratively down down
"""
        result = parse_interfaces(output)
        assert len(result) == 3
        assert result[0]["interface"] == "GigabitEthernet0/0"
        assert result[0]["ip_address"] == "192.168.1.1"
        assert result[0]["status"] == "up"

    def test_empty_output(self):
        assert parse_interfaces("") == []

    def test_header_only(self):
        assert parse_interfaces("Interface  IP-Address  OK? Method Status Protocol") == []


class TestParseArpTable:
    def test_cisco_arp(self):
        output = """
Protocol  Address          Age  Hardware Addr   Interface
Internet  192.168.1.1      120  aabb.cc00.1100  GigabitEthernet0/0
Internet  192.168.1.2       0   Incomplete      GigabitEthernet0/0
"""
        result = parse_arp_table(output)
        assert len(result) == 2
        assert result[0]["address"] == "192.168.1.1"
        assert result[0]["mac"] == "aabb.cc00.1100"

    def test_empty_output(self):
        assert parse_arp_table("") == []


class TestParsePing:
    def test_linux_ping_success(self):
        output = """PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.
64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=5.3 ms
64 bytes from 8.8.8.8: icmp_seq=2 ttl=118 time=4.8 ms

--- 8.8.8.8 ping statistics ---
4 packets transmitted, 4 received, 0% packet loss, time 3005ms
rtt min/avg/max = 4.832/5.051/5.312 ms
"""
        result = parse_ping(output)
        assert result["success"] is True
        assert result["sent"] == 4
        assert result["received"] == 4
        assert result["avg_rtt"] == 5.051

    def test_linux_ping_failure(self):
        output = """PING 10.255.255.1 (10.255.255.1) 56(84) bytes of data.

--- 10.255.255.1 ping statistics ---
4 packets transmitted, 0 received, 100% packet loss, time 3000ms
"""
        result = parse_ping(output)
        assert result["success"] is False
        assert result["sent"] == 4
        assert result["received"] == 0

    def test_cisco_ping_success(self):
        output = """Type escape sequence to abort.
Sending 5, 100-byte ICMP Echos to 192.168.1.1, timeout is 2 seconds:
!!!!!
Success rate is 100 percent (5/5), round-trip min/avg/max = 1/2/4 ms
"""
        result = parse_ping(output)
        assert result["success"] is True
        assert result["sent"] == 5
        assert result["received"] == 5

    def test_cisco_ping_failure(self):
        output = """Type escape sequence to abort.
Sending 5, 100-byte ICMP Echos to 10.0.0.99, timeout is 2 seconds:
.....
Success rate is 0 percent (0/5)
"""
        result = parse_ping(output)
        assert result["success"] is False
        assert result["sent"] == 5
        assert result["received"] == 0

    def test_empty_output(self):
        result = parse_ping("")
        assert result["success"] is False


class TestParseRoutingTable:
    def test_cisco_routes(self):
        output = """
Codes: L - local, C - connected, S - static, R - RIP, O - OSPF

Gateway of last resort is 192.168.1.254 to network 0.0.0.0

S*   0.0.0.0/0 [1/0] via 192.168.1.254
     10.0.0.0/8 is variably subnetted, 2 subnets, 2 masks
C       10.0.0.0/24 is directly connected, GigabitEthernet0/1
"""
        result = parse_routing_table(output)
        # Should parse at least some routes
        assert len(result) >= 1

    def test_empty_output(self):
        assert parse_routing_table("") == []


class TestParseVersion:
    def test_cisco_version(self):
        output = """Cisco IOS Software, C2960 Software (C2960-LANBASEK9-M), Version 15.0(2)SE4
Copyright (c) 1986-2013 by Cisco Systems, Inc.
Compiled Wed 26-Jun-13 02:49 by prod_rel_team

ROM: Bootstrap program is C2960 boot loader
BOOTLDR: C2960 Boot Loader (C2960-HBOOT-M) Version 12.2(25r)FX, RELEASE SOFTWARE (fc4)

Switch uptime is 2 years, 3 weeks, 2 days, 5 hours, 23 minutes
System returned to ROM by power-on
System image file is "flash:/c2960-lanbasek9-mz.150-2.SE4.bin"

Model Number: WS-C2960-24TT-L
Serial Number: FOC1234X5Y6
Hostname: switch-floor1
"""
        result = parse_version(output)
        assert "version" in result
        assert "uptime" in result
        assert result["uptime"] == "2 years, 3 weeks, 2 days, 5 hours, 23 minutes"

    def test_empty_output(self):
        assert parse_version("") == {}


class TestExtractIps:
    def test_find_ips(self):
        text = "Connected to 192.168.1.1 and 10.0.0.1 via 172.16.0.1"
        ips = extract_ips(text)
        assert "192.168.1.1" in ips
        assert "10.0.0.1" in ips
        assert "172.16.0.1" in ips

    def test_no_ips(self):
        assert extract_ips("no ips here") == []


class TestExtractMacs:
    def test_colon_format(self):
        text = "MAC: aa:bb:cc:dd:ee:ff"
        macs = extract_macs(text)
        assert "aa:bb:cc:dd:ee:ff" in macs

    def test_dash_format(self):
        text = "MAC: aa-bb-cc-dd-ee-ff"
        macs = extract_macs(text)
        assert "aa-bb-cc-dd-ee-ff" in macs

    def test_no_macs(self):
        assert extract_macs("no macs here") == []
