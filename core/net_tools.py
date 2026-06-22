"""Sentinel Desktop v15.0 — Network diagnostic tools.

DNS lookup, ping, traceroute, port scan — all via stdlib or system
commands (no new dependencies).

Usage::

    from core.net_tools import dns_lookup, ping_host, port_open

    result = dns_lookup("google.com")
    # {"hostname": "google.com", "addresses": ["142.250.80.46"], "type": "A"}

    ok, rtt = ping_host("8.8.8.8", count=4)
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"

# Hostname/IP literal charset. Leading dashes are rejected separately (they
# are argument-injection into ping/traceroute, which parse a leading-dash
# token as a flag). Whitespace and shell metacharacters are excluded.
_VALID_HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._:-]*[A-Za-z0-9])?$")


def _validate_host(host: str) -> str | None:
    """Return *host* if it is a safe hostname/IP literal, else None.

    Rejects empty/non-strings, leading dashes (ping/traceroute flag
    injection), values over 253 chars, and any character outside the DNS/IPv6
    set. IPv6 and IPv4 literals are accepted via ipaddress first.
    """
    if not isinstance(host, str) or not host:
        return None
    if host.startswith("-"):
        return None
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    if len(host) > 253:
        return None
    return host if _VALID_HOST_RE.match(host) else None


# ── DNS ──────────────────────────────────────────────────────────────────────


def dns_lookup(
    hostname: str,
    record_type: str = "A",
    server: str | None = None,
) -> dict[str, Any]:
    """Resolve *hostname* and return addresses.

    Args:
        hostname:    The name to resolve. Can also be an IP for reverse lookup.
        record_type: ``"A"`` (IPv4), ``"AAAA"`` (IPv6), ``"PTR"`` (reverse),
                     ``"MX"``, ``"TXT"``. Default ``"A"``.
        server:      Optional DNS server to query (uses dnspython if available).

    Returns:
        Dict with ``hostname``, ``addresses`` list, ``type``, and
        optionally ``error``.
    """
    record_type = record_type.upper()

    # Try dnspython for full record type support (optional dep)
    if record_type in ("MX", "TXT", "NS", "CNAME") or server:
        result = _dns_lookup_dnspython(hostname, record_type, server)
        if result:
            return result

    # Standard socket-based lookup
    return _dns_lookup_socket(hostname, record_type)


def _dns_lookup_socket(hostname: str, record_type: str) -> dict[str, Any]:
    """Resolve using stdlib socket — covers A, AAAA, PTR."""
    try:
        # Detect if input is an IP (for reverse lookup)
        try:
            ipaddress.ip_address(hostname)
            is_ip = True
        except ValueError:
            is_ip = False

        if record_type == "PTR" or (is_ip and record_type == "A"):
            name, _, _ = socket.gethostbyaddr(hostname)
            return {"hostname": hostname, "addresses": [name], "type": "PTR"}

        if record_type == "AAAA":
            infos = socket.getaddrinfo(hostname, None, socket.AF_INET6)
            addrs = list({info[4][0] for info in infos})
        else:
            infos = socket.getaddrinfo(hostname, None, socket.AF_INET)
            addrs = list({info[4][0] for info in infos})

        return {"hostname": hostname, "addresses": addrs, "type": record_type}
    except socket.gaierror as exc:
        return {"hostname": hostname, "addresses": [], "type": record_type, "error": str(exc)}
    except socket.herror as exc:
        return {"hostname": hostname, "addresses": [], "type": record_type, "error": str(exc)}


def _dns_lookup_dnspython(
    hostname: str, record_type: str, server: str | None
) -> dict[str, Any] | None:
    """Resolve using dnspython for advanced record types."""
    try:
        import dns.resolver  # type: ignore

        resolver = dns.resolver.Resolver()
        if server:
            resolver.nameservers = [server]
        answers = resolver.resolve(hostname, record_type)
        addrs = [str(rdata) for rdata in answers]
        return {"hostname": hostname, "addresses": addrs, "type": record_type}
    except ImportError:
        return None
    except Exception as exc:
        return {"hostname": hostname, "addresses": [], "type": record_type, "error": str(exc)}


# ── Ping ─────────────────────────────────────────────────────────────────────


def ping_host(host: str, count: int = 4, timeout: int = 3) -> dict[str, Any]:
    """Ping *host* and return latency stats.

    Args:
        host:    Target hostname or IP.
        count:   Number of ICMP packets. Default 4.
        timeout: Per-packet timeout in seconds.

    Returns:
        Dict with ``success``, ``host``, ``packets_sent``,
        ``packets_received``, ``avg_ms``, and ``output``.
    """
    count = max(1, min(10, count))
    safe = _validate_host(host)
    if safe is None:
        return {"success": False, "host": host, "error": "invalid_host", "output": ""}
    host = safe
    if _IS_WINDOWS:
        cmd = ["ping", "-n", str(count), "-w", str(timeout * 1000), host]
    else:
        # "--" terminates option parsing so a (validated) host can never be
        # re-interpreted as a ping flag.
        cmd = ["ping", "-c", str(count), "-W", str(timeout), "--", host]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout * count + 5,
            check=False,
        )
        output = result.stdout + result.stderr
        return _parse_ping_output(host, output, count)
    except subprocess.TimeoutExpired:
        return {"success": False, "host": host, "error": "timeout", "output": ""}
    except OSError as exc:
        return {"success": False, "host": host, "error": str(exc), "output": ""}


def _parse_ping_output(host: str, output: str, count: int) -> dict[str, Any]:
    """Extract stats from ping command output."""
    received = 0
    avg_ms = None

    # Windows: "Received = 4"
    m = re.search(r"Received\s*=\s*(\d+)", output, re.IGNORECASE)
    if m:
        received = int(m.group(1))

    # Unix: "4 received" or "4 packets received"
    m = re.search(r"(\d+)\s+(?:packets?\s+)?received", output, re.IGNORECASE)
    if m:
        received = int(m.group(1))

    # Windows avg: "Average = 12ms"
    m = re.search(r"Average\s*=\s*(\d+)\s*ms", output, re.IGNORECASE)
    if m:
        avg_ms = float(m.group(1))

    # Unix avg: "rtt min/avg/max/mdev = 0.5/1.2/2.0/0.3 ms"
    m = re.search(r"min/avg/max.*?=\s*[\d.]+/([\d.]+)", output)
    if m:
        avg_ms = float(m.group(1))

    return {
        "success": received > 0,
        "host": host,
        "packets_sent": count,
        "packets_received": received,
        "avg_ms": avg_ms,
        "output": output[:2000],
    }


# ── Port scan ────────────────────────────────────────────────────────────────


def port_open(host: str, port: int, timeout: float = 3.0) -> bool:
    """Return True if *host*:*port* accepts a TCP connection."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, OSError):
        return False


def scan_ports(
    host: str,
    ports: list[int],
    timeout: float = 2.0,
) -> dict[int, bool]:
    """Scan a list of TCP ports on *host*.

    Returns dict mapping port → open(bool).
    """
    return {p: port_open(host, p, timeout=timeout) for p in ports}


# ── Traceroute ───────────────────────────────────────────────────────────────


def traceroute(host: str, max_hops: int = 30) -> dict[str, Any]:
    """Run a traceroute to *host* and return structured hops.

    Returns:
        Dict with ``host``, ``hops`` (list of dicts), and ``output``.
    """
    safe = _validate_host(host)
    if safe is None:
        return {"host": host, "hops": [], "error": "invalid_host", "output": ""}
    host = safe
    if _IS_WINDOWS:
        cmd = ["tracert", "-d", "-h", str(max_hops), host]
    else:
        cmd = ["traceroute", "-n", "-m", str(max_hops), "--", host]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max_hops * 5 + 10,
            check=False,
        )
        output = result.stdout + result.stderr
        hops = _parse_traceroute(output)
        return {"host": host, "hops": hops, "output": output[:5000]}
    except subprocess.TimeoutExpired:
        return {"host": host, "hops": [], "error": "timeout", "output": ""}
    except OSError as exc:
        return {"host": host, "hops": [], "error": str(exc), "output": ""}


def _parse_traceroute(output: str) -> list[dict[str, Any]]:
    """Extract hops from traceroute/tracert output."""
    hops = []
    for line in output.splitlines():
        # Windows: "  1     1 ms     1 ms     1 ms  192.168.1.1"
        # Unix:    "  1  192.168.1.1  1.234 ms  0.987 ms  0.876 ms"
        m = re.match(r"\s*(\d+)\s+.*?([\d.]+\.\d+\.\d+\.\d+|[*]+)", line)
        if m:
            hops.append({"hop": int(m.group(1)), "address": m.group(2)})
    return hops
