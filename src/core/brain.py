"""
Neuralis Brain AI Client
Connects to the Neuralis Brain REST API for Claude-like reasoning.
"""
import requests
import logging
from src.config import BRAIN_URL, BRAIN_TIMEOUT

logger = logging.getLogger(__name__)


class BrainClient:
    """Client for Neuralis Brain REST API."""

    def __init__(self, url: str = None):
        self.url = url or BRAIN_URL
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def health(self) -> dict:
        """Check brain online status."""
        try:
            r = self.session.get(f"{self.url}/health", timeout=BRAIN_TIMEOUT)
            return r.json() if r.status_code == 200 else {"status": "error", "code": r.status_code}
        except Exception as e:
            logger.error(f"Brain health check failed: {e}")
            return {"status": "offline", "error": str(e)}

    def stats(self) -> dict:
        """Get neuron counts and uptime."""
        try:
            r = self.session.get(f"{self.url}/stats", timeout=BRAIN_TIMEOUT)
            return r.json() if r.status_code == 200 else {}
        except Exception as e:
            logger.error(f"Brain stats failed: {e}")
            return {"error": str(e)}

    def recall(self, context: str) -> list:
        """Look up knowledge from the brain."""
        try:
            r = self.session.post(
                f"{self.url}/recall",
                json={"context": context},
                timeout=BRAIN_TIMEOUT,
            )
            if r.status_code == 200:
                return r.json().get("results", [])
            return []
        except Exception as e:
            logger.error(f"Brain recall failed: {e}")
            return []

    def search(self, query: str) -> list:
        """Search neurons in the brain."""
        try:
            r = self.session.post(
                f"{self.url}/search",
                json={"q": query},
                timeout=BRAIN_TIMEOUT,
            )
            if r.status_code == 200:
                return r.json().get("results", [])
            return []
        except Exception as e:
            logger.error(f"Brain search failed: {e}")
            return []

    def think(self, topic: str, content: str, region: str = "general") -> dict:
        """Store knowledge in the brain."""
        try:
            r = self.session.post(
                f"{self.url}/think",
                json={"topic": topic, "content": content, "region": region},
                timeout=BRAIN_TIMEOUT,
            )
            return r.json() if r.status_code == 200 else {}
        except Exception as e:
            logger.error(f"Brain think failed: {e}")
            return {"error": str(e)}

    def regions(self) -> list:
        """List brain regions."""
        try:
            r = self.session.get(f"{self.url}/regions", timeout=BRAIN_TIMEOUT)
            return r.json().get("regions", []) if r.status_code == 200 else []
        except Exception as e:
            logger.error(f"Brain regions failed: {e}")
            return []

    def ask(self, prompt: str, context: str = "") -> str:
        """Ask the brain a question - high-level reasoning."""
        # First recall relevant knowledge
        knowledge = self.recall(prompt) if context else self.search(prompt)
        knowledge_text = "\n".join(
            [f"- {k.get('topic', '')}: {k.get('content', '')}" for k in knowledge[:5]]
        )
        return knowledge_text or "No relevant knowledge found in brain."
