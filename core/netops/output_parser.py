"""Sentinel Desktop v9.0 — Network command output parser.

Parses structured data from common network device outputs:
- Interface tables
- ARP tables
- Routing tables
- Ping results
- Version info

Returns lists of dicts for easy consumption by the agent.
"""

from __future__ import annotations

import re
from typing import Any


def parse_interfaces(output: str) -> list[dict[str, str]]:
    """Parse interface table output into structured data.

    Handles Cisco IOS 'show ip interface brief' format and similar.

    Returns:
        List of dicts with keys: interface, ip_address, status, protocol.
    """
    interfaces = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("Interface") or line.startswith("---"):
            continue

        # Cisco IOS format: Interface  IP-Address  OK?  Method  Status  Protocol
        parts = line.split()
        if len(parts) >= 6:
            interfaces.append(
                {
                    "interface": parts[0],
                    "ip_address": parts[1],
                    "status": parts[-2] if len(parts) >= 6 else "unknown",
                    "protocol": parts[-1],
                }
            )
        elif len(parts) >= 2:
            interfaces.append(
                {
                    "interface": parts[0],
                    "ip_address": parts[1] if len(parts) > 1 else "",
                    "status": "unknown",
                    "protocol": "unknown",
                }
            )

    return interfaces


def parse_arp_table(output: str) -> list[dict[str, str]]:
    """Parse ARP table output into structured data.

    Returns:
        List of dicts with keys: protocol, address, age, mac, interface.
    """
    entries = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("Protocol") or line.startswith("---"):
            continue

        parts = line.split()
        if len(parts) >= 4:
            entries.append(
                {
                    "protocol": parts[0] if len(parts) > 3 else "",
                    "address": parts[1],
                    "age": parts[2] if len(parts) > 3 else "",
                    "mac": parts[3] if len(parts) > 3 else parts[2],
                    "interface": parts[-1],
                }
            )

    return entries


def parse_ping(output: str) -> dict[str, Any]:
    """Parse ping output for success/failure and stats.

    Returns:
        Dict with: success, sent, received, loss_percent, avg_rtt, host.
    """
    result: dict[str, Any] = {
        "success": False,
        "sent": 0,
        "received": 0,
        "loss_percent": 100.0,
        "avg_rtt": None,
        "host": "",
    }

    # Extract host
    host_match = re.search(r"ping\s+(\S+)", output, re.IGNORECASE)
    if host_match:
        result["host"] = host_match.group(1)

    # Cisco: "Success rate is X percent (Y/Z)"
    cisco_match = re.search(r"Success rate is (\d+) percent \((\d+)/(\d+)\)", output)
    if cisco_match:
        result["success"] = int(cisco_match.group(1)) > 0
        result["received"] = int(cisco_match.group(2))
        result["sent"] = int(cisco_match.group(3))
        result["loss_percent"] = 100.0 - (result["received"] / max(result["sent"], 1)) * 100
        return result

    # Linux: "X packets transmitted, Y received, Z% packet loss"
    linux_match = re.search(
        r"(\d+) packets transmitted,?\s+(\d+) received,?\s+[\d.]+% packet loss",
        output,
    )
    if linux_match:
        result["sent"] = int(linux_match.group(1))
        result["received"] = int(linux_match.group(2))
        result["success"] = result["received"] > 0
        result["loss_percent"] = (1 - result["received"] / max(result["sent"], 1)) * 100

    # RTT: "rtt min/avg/max = X/Y/Z ms" or "round-trip min/avg/max = X/Y/Z ms"
    rtt_match = re.search(r"(?:rtt|round-trip)[^=]*=\s*[\d.]+/([\d.]+)/[\d.]+", output)
    if rtt_match:
        result["avg_rtt"] = float(rtt_match.group(1))

    # Also check for "Reply from" (Windows ping)
    if "Reply from" in output or "reply from" in output.lower():
        result["success"] = True

    return result


def parse_traceroute(output: str) -> dict[str, Any]:
    """Parse traceroute output for hops and path.

    Returns:
        Dict with: success, target, hops (list of hop dicts),
        total_hops, reached_target.
    """
    result: dict[str, Any] = {
        "success": False,
        "target": "",
        "hops": [],
        "total_hops": 0,
        "reached_target": False,
    }

    # Extract target from first line
    target_match = re.search(
        r"traceroute\s+(?:to\s+)?(\S+)",
        output,
        re.IGNORECASE,
    )
    if target_match:
        result["target"] = target_match.group(1)

    # Cisco: " 1 10.0.0.1 4 msec 4 msec 4 msec"
    # Also:  " 1 192.168.1.1 1.0 ms 1.0 ms 1.0 ms"
    cisco_hop = re.compile(
        r"^\s*(\d+)\s+"
        r"(\S+)"  # IP or hostname
        r"(?:\s+\([\d.]+\))?"  # optional (resolved IP)
        r"((?:\s+[\d.]+\s*m?s(?:ec)?|\s+\*)+)",
        re.MULTILINE,
    )
    # Linux: " 1  gateway (192.168.1.1)  0.456 ms  0.398 ms  0.382 ms"
    linux_hop = re.compile(
        r"^\s*(\d+)\s+"
        r"(\S+)"  # hostname
        r"\s+\(([\d.]+)\)"  # (IP)
        r"((?:\s+[\d.]+\s*m?s(?:ec)?|\s+\*)+)",
        re.MULTILINE,
    )

    for pattern in (linux_hop, cisco_hop):
        for m in pattern.finditer(output):
            hop_num = int(m.group(1))
            host = m.group(2)
            timings_raw = m.group(m.lastindex)

            # Extract timing values (handles ms, msec, and * hops)
            times = re.findall(
                r"([\d.]+)\s*m?s(?:ec)?",
                timings_raw,
            )
            avg_rtt = None
            if times:
                avg_rtt = round(
                    sum(float(t) for t in times) / len(times),
                    2,
                )

            hop = {
                "hop": hop_num,
                "host": host,
                "avg_rtt_ms": avg_rtt,
            }
            # Avoid duplicates (Cisco may match with both patterns)
            if not any(h["hop"] == hop_num for h in result["hops"]):
                result["hops"].append(hop)

    result["total_hops"] = len(result["hops"])

    # Check if target was reached
    if result["hops"]:
        last = result["hops"][-1]
        target_ip = result["target"].strip("()\"'")
        if last["host"] == target_ip or last["host"] == result["target"]:
            result["reached_target"] = True

    result["success"] = result["total_hops"] > 0
    return result


def parse_routing_table(output: str) -> list[dict[str, str]]:
    """Parse routing table output.

    Returns:
        List of dicts with keys: destination, gateway, interface, etc.
    """
    routes = []
    for line in output.splitlines():
        line = line.strip()
        _skip_prefixes = ("Codes", "Destination", "---", "Kernel")
        if not line or any(line.startswith(p) for p in _skip_prefixes):
            continue

        parts = line.split()
        if len(parts) >= 3:
            routes.append(
                {
                    "destination": parts[0],
                    "gateway": parts[1] if len(parts) > 1 else "",
                    "interface": parts[-1],
                    "raw": line,
                }
            )

    return routes


def parse_version(output: str) -> dict[str, str]:
    """Parse device version info into key-value pairs.

    Returns:
        Dict with extracted version details.
    """
    info: dict[str, str] = {}

    # Extract common patterns
    for pattern, key in [
        (r"([Cc]isco\s+\w+ Software.*)", "software"),
        (r"[Vv]ersion\s+([\S]+)", "version"),
        (r"([Cc]isco\s+\w+)\s+\(.*?\)\s+.*", "platform"),
        (r"uptime is (.*)", "uptime"),
        (r"JUNOS\s+.*\s+\[([^]]+)\]", "junos_version"),
        (r"Model(?:\s+Number)?:\s+(\S+)", "model"),
        (r"Serial(?:\s+Number)?:\s+(\S+)", "serial"),
        (r"Hostname:\s+(\S+)", "hostname"),
    ]:
        match = re.search(pattern, output)
        if match:
            info[key] = match.group(1).strip()

    return info


def extract_ips(output: str) -> list[str]:
    """Extract all IP addresses from text.

    Returns:
        List of IP address strings.
    """
    return re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", output)


def extract_macs(output: str) -> list[str]:
    """Extract all MAC addresses from text.

    Returns:
        List of MAC address strings.
    """
    return re.findall(r"(?:[0-9a-fA-F]{2}[:\-]){5}[0-9a-fA-F]{2}", output)
