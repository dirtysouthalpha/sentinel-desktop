"""Sentinel Desktop v9.0 — Netops subpackage.

SSH/network device control for IT automation. Connect to routers, switches,
firewalls, and other network devices via SSH, run commands, parse output.
"""

from core.netops.command_runner import CommandRunner
from core.netops.ssh_client import SSHClient

__all__ = ["SSHClient", "CommandRunner"]
