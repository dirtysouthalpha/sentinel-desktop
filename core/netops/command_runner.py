"""Sentinel Desktop v9.0 — Network command runner.

High-level interface for running common network device commands.
Knows the command syntax for Cisco IOS, Juniper JunOS, FortiGate,
SonicWall, MikroTik, pfSense, and generic Linux.

Dispatches to SSHClient under the hood.
"""

from __future__ import annotations

import logging

from core.net_tools import _validate_host
from core.netops.ssh_client import SSHClient, SSHResult

logger = logging.getLogger(__name__)

# Device OS types with their command prefixes
DEVICE_TYPES = {
    "cisco_ios": "Cisco IOS/IOS-XE",
    "cisco_nxos": "Cisco NX-OS",
    "juniper_junos": "Juniper JunOS",
    "fortigate": "FortiGate FortiOS",
    "sonicwall": "SonicWall SonicOS",
    "mikrotik": "MikroTik RouterOS",
    "pfsense": "pfSense (FreeBSD)",
    "linux": "Generic Linux",
    "generic": "Unknown/Generic",
}


class CommandRunner:
    """Run network commands with device-specific syntax awareness.

    Usage::

        runner = CommandRunner(ssh_client, device_type="cisco_ios")
        result = runner.show_version()
        result = runner.show_interfaces()
        result = runner.ping("8.8.8.8")
    """

    def __init__(
        self,
        ssh_client: SSHClient,
        device_type: str = "generic",
    ) -> None:
        if device_type not in DEVICE_TYPES:
            raise ValueError(
                f"unknown device_type {device_type!r}; valid options: "
                f"{sorted(DEVICE_TYPES)}"
            )
        self.client = ssh_client
        self.device_type = device_type

    # ── Show commands ──────────────────────────────────────────────────

    def show_version(self) -> SSHResult:
        """Run 'show version' (or equivalent)."""
        cmd = self._cmd(
            "show version",
            "show version",
            "show system",
            "system/resource",
            "/system/resource/print",
            "uname -a",
        )
        return self.client.run_command(cmd)

    def show_interfaces(self) -> SSHResult:
        """Run 'show interfaces' (or equivalent)."""
        cmd = self._cmd(
            cisco_ios="show ip interface brief",
            cisco_nxos="show interface",
            juniper="show interface terse",
            fortigate="get system interface",
            mikrotik="/interface/print",
            linux="ip addr",
        )
        return self.client.run_command(cmd)

    def show_routing(self) -> SSHResult:
        """Show routing table."""
        cmd = self._cmd(
            cisco_ios="show ip route",
            cisco_nxos="show route",
            juniper="show route",
            fortigate="get router info routing-table all",
            mikrotik="/ip route print",
            linux="ip route",
        )
        return self.client.run_command(cmd)

    def show_arp(self) -> SSHResult:
        """Show ARP table."""
        cmd = self._cmd(
            cisco_ios="show ip arp",
            cisco_nxos="show arp",
            juniper="show arp",
            fortigate="get system arp",
            mikrotik="/ip arp print",
            linux="arp -a",
        )
        return self.client.run_command(cmd)

    def show_running_config(self) -> SSHResult:
        """Show running configuration."""
        cmd = self._cmd(
            cisco_ios="show running-config",
            cisco_nxos="show running-config",
            juniper="show configuration",
            fortigate="show full-configuration",
            mikrotik="/export",
            linux="cat /etc/rc.conf",
        )
        return self.client.run_command(cmd)

    # ── Diagnostic commands ────────────────────────────────────────────

    def ping(self, target: str, count: int = 4) -> SSHResult:
        """Ping a target host."""
        # Validate the target before interpolating it into a device command
        # string — same argument-injection class fixed in net_tools.ping_host.
        # An unchecked target let "; write erase" or "\nreboot" reach the
        # device shell via SSH exec_command.
        safe = _validate_host(target)
        if safe is None:
            return SSHResult(
                success=False,
                stdout="",
                stderr=f"invalid host: {target!r}",
                exit_code=None,
                command="",
                duration_ms=0.0,
            )
        target = safe
        count = max(1, min(10, int(count)))
        cmds = {
            "cisco_ios": f"ping {target} repeat {count}",
            "cisco_nxos": f"ping {target} count {count}",
            "juniper_junos": f"ping {target} count {count}",
            "fortigate": f"execute ping {target}",
            "mikrotik": f"/ping {target} count={count}",
            "linux": f"ping -c {count} {target}",
            "generic": f"ping -c {count} {target}",
        }
        cmd = cmds.get(self.device_type, f"ping -c {count} {target}")
        return self.client.run_command(cmd)

    def traceroute(self, target: str) -> SSHResult:
        """Traceroute to a target."""
        safe = _validate_host(target)
        if safe is None:
            return SSHResult(
                success=False,
                stdout="",
                stderr=f"invalid host: {target!r}",
                exit_code=None,
                command="",
                duration_ms=0.0,
            )
        target = safe
        cmds = {
            "cisco_ios": f"traceroute {target}",
            "cisco_nxos": f"traceroute {target}",
            "juniper_junos": f"traceroute {target}",
            "fortigate": f"execute traceroute {target}",
            "mikrotik": f"/tool traceroute {target}",
            "linux": f"traceroute {target}",
            "generic": f"traceroute {target}",
        }
        cmd = cmds.get(self.device_type, f"traceroute {target}")
        return self.client.run_command(cmd)

    def show_logging(self, lines: int = 50) -> SSHResult:
        """Show recent log entries."""
        cmds = {
            "cisco_ios": f"show logging | last {lines}",
            "cisco_nxos": f"show logging last {lines}",
            "juniper_junos": f"show log messages | last {lines}",
            "linux": f"tail -n {lines} /var/log/syslog",
            "generic": f"tail -n {lines} /var/log/syslog",
        }
        cmd = cmds.get(self.device_type, f"tail -n {lines} /var/log/syslog")
        return self.client.run_command(cmd)

    def show_cpu(self) -> SSHResult:
        """Show CPU utilization."""
        cmds = {
            "cisco_ios": "show processes cpu",
            "cisco_nxos": "show processes cpu",
            "juniper_junos": "show chassis routing-engine",
            "fortigate": "get system performance status",
            "mikrotik": "/system resource print",
            "linux": "top -bn1 | head -5",
            "generic": "top -bn1 | head -5",
        }
        cmd = cmds.get(self.device_type, "top -bn1 | head -5")
        return self.client.run_command(cmd)

    def run_raw(self, command: str) -> SSHResult:
        """Run a raw command string on the device."""
        return self.client.run_command(command)

    def _cmd(
        self,
        cisco_ios: str = "",
        cisco_nxos: str = "",
        juniper: str = "",
        fortigate: str = "",
        mikrotik: str = "",
        linux: str = "",
    ) -> str:
        """Select the right command for the device type."""
        mapping = {
            "cisco_ios": cisco_ios,
            "cisco_nxos": cisco_nxos,
            "juniper_junos": juniper,
            "fortigate": fortigate,
            "mikrotik": mikrotik,
            "pfsense": linux,
            "linux": linux,
            "generic": linux or cisco_ios,
        }
        return mapping.get(self.device_type, linux or cisco_ios)
