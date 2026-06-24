"""LLM client for Hatz.ai - powers the agent planner and conversational AI."""
import os
import json
import logging
import requests

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for Hatz.ai API (OpenAI-compatible)."""

    def __init__(self, api_key=None, model="gpt-4o", base_url="https://ai.hatz.ai/v1"):
        self.api_key = api_key or os.environ.get("HATZ_API_KEY", "")
        self.model = model
        self.base_url = base_url
        self.timeout = 30

    def chat(self, messages, temperature=0.7, max_tokens=2000):
        """Send a chat completion request."""
        if not self.api_key:
            return None
        try:
            r = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM chat failed: {e}")
            return None

    def plan(self, user_request, available_commands):
        """Ask LLM to decompose a complex request into executable steps."""
        system_prompt = (
            "You are Sentinel Desktop's task planner. Break down the user's request into "
            "a sequence of executable commands. Only use commands from the available list. "
            "Return a JSON array of command strings. Be concise and practical.\n\n"
            f"Available commands: {json.dumps(available_commands)}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_request},
        ]
        response = self.chat(messages, temperature=0.3, max_tokens=500)
        if not response:
            return None
        try:
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                plan = json.loads(response[start:end])
                return [str(step) for step in plan if step]
        except json.JSONDecodeError:
            pass
        lines = [l.strip().lstrip("0123456789.-) ") for l in response.split("\n") if l.strip()]
        return lines if lines else None

    def converse(self, user_message, context=""):
        """Natural language conversation using LLM."""
        system = (
            "You are Sentinel Desktop, an AI desktop assistant. You help with system monitoring, "
            "automation, web browsing, and task execution. Be friendly, concise, and helpful. "
            "Keep responses under 3 sentences unless asked for detail."
        )
        messages = [
            {"role": "system", "content": system},
        ]
        if context:
            messages.append({"role": "assistant", "content": context})
        messages.append({"role": "user", "content": user_message})
        return self.chat(messages, temperature=0.7, max_tokens=300)
