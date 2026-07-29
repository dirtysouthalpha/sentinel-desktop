"""Fleet mesh deployment script.

Generates per-node JSON configuration files for a multi-node Sentinel
Desktop fleet mesh, performs dry-run previews, and (optionally) triggers
deployment via ``systemctl`` or ``docker compose``.

Usage:
    python -m deploy.deploy_fleet --generate
    python -m deploy.deploy_fleet --dry-run
    python -m deploy.deploy_fleet --deploy
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fleet topology
# ---------------------------------------------------------------------------

FLEET_NODES: list[dict[str, Any]] = [
    {
        "node_id": "cns-main",
        "priority": "cns",
        "port": 4433,
        "host": "cns-main.fleet.local",
        "peers": ["prime-main.fleet.local:4434", "desktop-main.fleet.local:4435"],
    },
    {
        "node_id": "prime-main",
        "priority": "prime",
        "port": 4434,
        "host": "prime-main.fleet.local",
        "peers": ["cns-main.fleet.local:4433", "desktop-main.fleet.local:4435"],
    },
    {
        "node_id": "desktop-main",
        "priority": "desktop",
        "port": 4435,
        "host": "desktop-main.fleet.local",
        "peers": ["cns-main.fleet.local:4433", "prime-main.fleet.local:4434"],
    },
]

_REQUIRED_FIELDS: tuple[str, ...] = ("node_id", "priority", "port", "host", "peers")
_VALID_PRIORITIES: set[str] = {"cns", "prime", "desktop", "agent_zero"}


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------

def _output_dir() -> Path:
    """Return the directory under which generated configs are written."""
    return Path(__file__).resolve().parent / "generated"


def generate_configs(nodes: list[dict[str, Any]] | None = None) -> Path:
    """Write one JSON config per node to ``deploy/generated/``.

    Args:
        nodes: Override the default ``FLEET_NODES`` list.  Defaults to
            :data:`FLEET_NODES` when ``None``.

    Returns:
        The path to the output directory.
    """
    nodes = nodes if nodes is not None else FLEET_NODES
    output_dir = _output_dir()
    os.makedirs(output_dir, exist_ok=True)

    for node in nodes:
        node_id = node["node_id"]
        config_path = output_dir / f"{node_id}.json"
        payload = {
            "node_id": node["node_id"],
            "priority": node["priority"],
            "port": node["port"],
            "host": node["host"],
            "peers": node["peers"],
        }
        config_path.write_text(json.dumps(payload, indent=2) + "\n")
        logger.info("Wrote config: %s", config_path)

    return output_dir


# ---------------------------------------------------------------------------
# Dry-run preview
# ---------------------------------------------------------------------------

def dry_run(nodes: list[dict[str, Any]] | None = None) -> str:
    """Return a formatted table summarising the fleet topology.

    Args:
        nodes: Override the default ``FLEET_NODES`` list.

    Returns:
        A multi-line string suitable for printing to a terminal.
    """
    nodes = nodes if nodes is not None else FLEET_NODES

    header = f"{'NODE ID':<18} {'PRIORITY':<12} {'PORT':<6} {'HOST':<30} {'PEERS'}"
    sep = "-" * len(header)
    lines = [sep, "Fleet Mesh Deployment Plan", sep, header, sep]

    for node in nodes:
        peers_str = ", ".join(node["peers"])
        lines.append(
            f"{node['node_id']:<18} {node['priority']:<12} {node['port']:<6} "
            f"{node['host']:<30} {peers_str}"
        )

    lines.append(sep)
    lines.append(f"Total nodes: {len(nodes)}")
    lines.append(sep)

    table = "\n".join(lines)
    print(table)
    return table


# ---------------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------------

def deploy(nodes: list[dict[str, Any]] | None = None) -> None:
    """Trigger deployment of the fleet.

    Currently a placeholder that logs intent.  A real implementation would
    invoke ``systemctl`` / ``docker compose`` / SSH to provision each node.
    """
    nodes = nodes if nodes is not None else FLEET_NODES
    logger.info("Deploying %d fleet nodes", len(nodes))
    for node in nodes:
        logger.info(
            "  -> %s (%s) on %s:%s",
            node["node_id"], node["priority"], node["host"], node["port"],
        )
    # Deployment logic goes here.
    logger.info("Deployment complete (no-op)")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate, preview, or deploy the Sentinel fleet mesh.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--generate",
        action="store_true",
        help="Write per-node JSON configs to deploy/generated/",
    )
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Print a deployment plan without making changes.",
    )
    group.add_argument(
        "--deploy",
        action="store_true",
        help="Trigger deployment of the fleet mesh.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.generate:
        out = generate_configs()
        print(f"Configs written to {out}")
    elif args.dry_run:
        dry_run()
    elif args.deploy:
        deploy()

    return 0


if __name__ == "__main__":
    sys.exit(main())
