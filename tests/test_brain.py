import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.legacy_brain import BrainClient


class TestBrainClient:
    def setup_method(self):
        self.brain = BrainClient("http://test:8001")

    def test_health_ok(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_session.get.return_value = mock_response
        self.brain.session = mock_session
        result = self.brain.health()
        assert result["status"] == "ok"

    def test_health_offline(self):
        mock_session = MagicMock()
        mock_session.get.side_effect = ConnectionError("refused")
        self.brain.session = mock_session
        result = self.brain.health()
        assert result["status"] == "offline"

    def test_recall(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [{"topic": "test", "content": "value"}]}
        mock_session.post.return_value = mock_response
        self.brain.session = mock_session
        results = self.brain.recall("test")
        assert len(results) == 1
        assert results[0]["topic"] == "test"

    def test_search_empty(self):
        mock_session = MagicMock()
        mock_session.post.side_effect = ConnectionError("refused")
        self.brain.session = mock_session
        results = self.brain.search("nothing")
        assert results == []

    def test_think(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1, "status": "stored"}
        mock_session.post.return_value = mock_response
        self.brain.session = mock_session
        result = self.brain.think("topic", "content")
        assert result["status"] == "stored"
