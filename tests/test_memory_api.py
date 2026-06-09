"""Tests for memory and conductor API endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def client():
    """Create a test client for the API server."""
    from fastapi.testclient import TestClient

    from api.server import SentinelServer

    server = SentinelServer(config={"api_token": "test"})
    app = server.create_app()
    return TestClient(app)


class TestMemoryAPIEndpoints:
    """Test memory REST API endpoints."""

    def test_list_facts(self, client):
        resp = client.get("/memory/facts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "keys" in data

    def test_store_and_get_fact(self, client):
        resp = client.post(
            "/memory/facts",
            json={
                "key": "test_key",
                "value": "test_value",
                "category": "test",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        resp = client.get("/memory/facts/test_key")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["data"]["value"] == "test_value"

    def test_get_nonexistent_fact(self, client):
        resp = client.get("/memory/facts/no_such_key_12345")
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_delete_fact(self, client):
        client.post(
            "/memory/facts",
            json={
                "key": "to_delete",
                "value": "delete me",
            },
        )
        resp = client.delete("/memory/facts/to_delete")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_delete_nonexistent(self, client):
        resp = client.delete("/memory/facts/no_such_key")
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_search_facts(self, client):
        client.post(
            "/memory/facts",
            json={
                "key": "search_test",
                "value": "searchable value",
                "category": "test",
                "tags": ["searchable"],
            },
        )
        resp = client.get("/memory/search", params={"query": "searchable"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["count"] >= 1

    def test_list_episodes(self, client):
        resp = client.get("/memory/episodes")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_search_episodes(self, client):
        resp = client.get("/memory/episodes/search", params={"query": "test"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestConductorAPIEndpoint:
    """Test conductor REST API endpoint."""

    def test_conductor_run(self, client):
        with patch("core.conductor.coordinator.Conductor") as MockConductor:

            mock = MagicMock()

            async def fake_run(goal, timeout=120.0):
                return {
                    "goal": goal,
                    "status": "success",
                    "success": True,
                    "summary": "Done",
                    "tasks_total": 1,
                    "tasks_succeeded": 1,
                    "tasks_failed": 0,
                    "results": [],
                }

            mock.run = fake_run
            MockConductor.return_value = mock

            resp = client.post(
                "/conductor/run",
                json={
                    "goal": "Check all firewalls",
                    "timeout": 60.0,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["data"]["status"] == "success"

    def test_conductor_run_error(self, client):
        with patch("core.conductor.coordinator.Conductor") as MockConductor:
            mock = MagicMock()

            async def failing_run(goal, timeout=120.0):
                raise RuntimeError("Boom")

            mock.run = failing_run
            MockConductor.return_value = mock

            resp = client.post("/conductor/run", json={"goal": "test"})
            assert resp.status_code == 200
            assert resp.json()["success"] is False
