"""Tests for the fleet deployment module (deploy/deploy_fleet.py)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deploy.deploy_fleet import FLEET_NODES, dry_run, generate_configs

# ---------------------------------------------------------------------------
# Fleet topology
# ---------------------------------------------------------------------------


class TestFleetNodes:
    """Validate the static FLEET_NODES topology definition."""

    def test_fleet_nodes_defined(self) -> None:
        assert len(FLEET_NODES) >= 2, "Expected at least 2 fleet nodes"

    def test_all_nodes_have_required_fields(self) -> None:
        required = {"node_id", "priority", "port", "host", "peers"}
        for node in FLEET_NODES:
            for field in required:
                assert field in node, f"Node {node.get('node_id', '?')} missing field '{field}'"

    def test_priorities_valid(self) -> None:
        valid = {"cns", "prime", "desktop", "agent_zero"}
        for node in FLEET_NODES:
            assert node["priority"] in valid, (
                f"Node {node['node_id']} has invalid priority '{node['priority']}'"
            )

    def test_ports_unique(self) -> None:
        ports = [node["port"] for node in FLEET_NODES]
        assert len(ports) == len(set(ports)), "Fleet node ports must be unique"

    def test_node_ids_unique(self) -> None:
        ids = [node["node_id"] for node in FLEET_NODES]
        assert len(ids) == len(set(ids)), "Fleet node IDs must be unique"


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


class TestGenerateConfigs:
    """Validate generate_configs() output."""

    def test_generate_creates_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Redirect the output directory into pytest's tmp_path.
        import deploy.deploy_fleet as mod

        monkeypatch.setattr(mod, "_output_dir", lambda: tmp_path)

        out = generate_configs()
        assert out == tmp_path

        for node in FLEET_NODES:
            config_path = tmp_path / f"{node['node_id']}.json"
            assert config_path.exists(), f"Missing config: {config_path}"
            data = json.loads(config_path.read_text())
            assert data["node_id"] == node["node_id"]
            assert data["priority"] == node["priority"]
            assert data["port"] == node["port"]
            assert data["host"] == node["host"]
            assert data["peers"] == node["peers"]

    def test_generate_overwrites(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import deploy.deploy_fleet as mod

        monkeypatch.setattr(mod, "_output_dir", lambda: tmp_path)

        # Calling twice must succeed without error and leave valid files.
        generate_configs()
        generate_configs()

        for node in FLEET_NODES:
            config_path = tmp_path / f"{node['node_id']}.json"
            assert config_path.exists()
            # Must still be valid JSON after the second write.
            json.loads(config_path.read_text())


# ---------------------------------------------------------------------------
# Dry-run preview
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_contains_all_nodes(self, capsys: pytest.CaptureFixture[str]) -> None:
        table = dry_run()
        captured = capsys.readouterr()
        # print() appends a trailing newline beyond the returned string.
        assert captured.out.rstrip("\n") == table.rstrip("\n")
        for node in FLEET_NODES:
            assert node["node_id"] in table
            assert node["host"] in table
