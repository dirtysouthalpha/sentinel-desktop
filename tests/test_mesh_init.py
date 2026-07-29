"""Tests for the mesh package."""
from core.mesh import EventBus, LeaderElection, MeshNode, Orchestrator


class TestMeshImport:
    def test_public_api_available(self):
        """Mesh package exposes core classes."""
        assert MeshNode is not None
        assert EventBus is not None
        assert LeaderElection is not None
        assert Orchestrator is not None
