"""Remote agent installation.

SentinelDesktop <host> — SSH in, detect OS, install headless agent, register with fleet.
"""

from __future__ import annotations

import logging
from typing import Any

from .fleet import Fleet, MachineInfo
from .ssh import SSHConfig, SSHExecutor

logger = logging.getLogger(__name__)

_INSTALL_SCRIPT_LINUX = r"""
set -e
echo "[sentinel] Installing on $(uname -a)"
# Create user if needed
id -u sentinel >/dev/null 2>&1 || useradd -r -m -s /bin/bash sentinel
# Install Python 3.10+ if missing
if ! command -v python3 >/dev/null 2>&1 || python3 -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)"; then
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -qq && apt-get install -y -qq python3 python3-venv python3-pip
    elif command -v yum >/dev/null 2>&1; then
        yum install -y python3 python3-pip
    elif command -v apk >/dev/null 2>&1; then
        apk add python3 py3-pip
    fi
fi
# Set up venv
sudo -u sentinel python3 -m venv /home/sentinel/sentinel-agent-venv
sudo -u sentinel /home/sentinel/sentinel-agent-venv/bin/pip install -q sentinel-desktop[headless]
# Create systemd service
cat > /etc/systemd/system/sentinel-agent.service << 'EOF'
[Unit]
Description=Sentinel Desktop Agent
After=network.target

[Service]
Type=simple
User=sentinel
WorkingDirectory=/home/sentinel
ExecStart=/home/sentinel/sentinel-agent-venv/bin/python -m sentinel_desktop --api --host 0.0.0.0 --port 8091
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now sentinel-agent
echo "[sentinel] Installed successfully on port 8091"
"""


class AgentInstaller:
    """Install Sentinel Desktop on remote machines."""

    def __init__(self, fleet: Fleet | None = None) -> None:
        self.fleet = fleet or Fleet()

    def install(self, host: str, user: str = "root", key_file: str = "",
                label: str = "", tags: list[str] | None = None, timeout: int = 300) -> bool:
        """Install agent on a remote host and add it to the fleet."""
        config = SSHConfig(host=host, user=user, key_file=key_file, timeout=timeout)
        executor = SSHExecutor(config)

        # Test connection first
        if not executor.test_connection():
            logger.error("Cannot connect to %s@%s", user, host)
            return False

        # Detect OS
        os_result = executor.run("uname -s")
        if not os_result.ok:
            logger.error("Cannot detect OS on %s", host)
            return False

        os_name = os_result.stdout.strip()
        if "Linux" not in os_name and "Darwin" not in os_name:
            logger.error("Unsupported OS: %s", os_name)
            return False

        # Run install script
        install_result = executor.run_script(_INSTALL_SCRIPT_LINUX, timeout=timeout)
        if not install_result.ok:
            logger.error("Install failed on %s: %s", host, install_result.stderr)
            return False

        # Register in fleet
        machine = MachineInfo(
            host=host, user=user, key_file=key_file,
            label=label or host, tags=tags or ["remote"],
            online=True,
        )
        self.fleet.register(machine)
        logger.info("Agent installed on %s and added to fleet", host)
        return True

    def uninstall(self, host: str, user: str = "root", key_file: str = "") -> bool:
        """Remove agent from a remote host."""
        config = SSHConfig(host=host, user=user, key_file=key_file)
        executor = SSHExecutor(config)

        if not executor.test_connection():
            return False

        # Stop and remove systemd service
        executor.run("systemctl stop sentinel-agent 2>/dev/null; systemctl disable sentinel-agent 2>/dev/null; rm -f /etc/systemd/system/sentinel-agent.service")
        executor.run("userdel -r sentinel 2>/dev/null || true")
        self.fleet.unregister(host)
        logger.info("Agent removed from %s", host)
        return True


__all__ = ["AgentInstaller"]
