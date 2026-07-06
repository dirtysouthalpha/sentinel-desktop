"""Web browsing and content fetching commands."""
import re
import subprocess
import platform
import webbrowser
from core.legacy_engine import CommandResult

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class WebCommands:
    """Open URLs, fetch content, and summarize web pages."""

    def open_url(self, url: str) -> CommandResult:
        """Open a URL in the default browser."""
        if not url.startswith("http"):
            url = "https://" + url
        try:
            webbrowser.open(url)
            return CommandResult(True, f"Opened in browser: {url}")
        except Exception as e:
            return CommandResult(False, f"Failed to open URL: {e}")

    def fetch(self, url: str) -> CommandResult:
        """Fetch a web page and extract readable text content."""
        if not HAS_REQUESTS:
            return CommandResult(False, "requests library not installed")
        if not url.startswith("http"):
            url = "https://" + url
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            html = r.text
            text = self._extract_text(html)
            title = self._extract_title(html)
            # Limit to first 2000 chars for display
            if len(text) > 2000:
                text = text[:2000] + "...\n\n[Content truncated]"
            return CommandResult(True, f"{title}\n\n{text}", {"url": url, "full_length": len(text)})
        except requests.exceptions.Timeout:
            return CommandResult(False, f"Timeout fetching {url}")
        except requests.exceptions.ConnectionError:
            return CommandResult(False, f"Could not connect to {url}")
        except Exception as e:
            return CommandResult(False, f"Fetch failed: {e}")

    def brief(self, url: str) -> CommandResult:
        """Fetch a web page and return a brief summary."""
        if not HAS_REQUESTS:
            return CommandResult(False, "requests library not installed")
        if not url.startswith("http"):
            url = "https://" + url
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            html = r.text
            title = self._extract_title(html)
            text = self._extract_text(html)
            # Build a brief - first 3 meaningful paragraphs or first 800 chars
            paragraphs = [p.strip() for p in text.split("\n") if len(p.strip()) > 50]
            brief_text = "\n\n".join(paragraphs[:5])
            if len(brief_text) > 1200:
                brief_text = brief_text[:1200] + "..."
            return CommandResult(True, f"BRIEF: {title}\n\n{brief_text}")
        except requests.exceptions.Timeout:
            return CommandResult(False, f"Timeout fetching {url}")
        except requests.exceptions.ConnectionError:
            return CommandResult(False, f"Could not connect to {url}")
        except Exception as e:
            return CommandResult(False, f"Brief failed: {e}")

    def search(self, query: str) -> CommandResult:
        """Search the web by opening browser to search results."""
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        return self.open_url(search_url)

    def _extract_title(self, html: str) -> str:
        """Extract page title from HTML."""
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return "(No title)"

    def _extract_text(self, html: str) -> str:
        """Extract readable text from HTML (basic, no external deps)."""
        # Remove scripts and styles
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<nav[^>]*>.*?</nav>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<footer[^>]*>.*?</footer>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<header[^>]*>.*?</header>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove all other tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()
        # Split into lines for readability
        sentences = text.split(". ")
        lines = []
        current = ""
        for s in sentences:
            current += s + ". "
            if len(current) > 100:
                lines.append(current.strip())
                current = ""
        if current:
            lines.append(current.strip())
        return "\n".join(lines)

    def execute(self, text: str) -> CommandResult:
        """Parse and execute web commands."""
        t = text.lower().strip()

        # Extract URL from text
        url_match = re.search(r"(https?://[^\s]+)", text)
        if not url_match:
            # Look for domain patterns
            domain_match = re.search(r"\b([a-z0-9-]+\.[a-z]{2,}[^\s]*)", text, re.IGNORECASE)
            if domain_match:
                url_match = domain_match

        url = url_match.group(1) if url_match else ""

        # Brief / summarize request
        if "brief" in t or "summary" in t or "summarize" in t:
            if url:
                return self.brief(url)
            return CommandResult(False, "Please provide a URL to summarize")

        # Fetch content
        if "fetch" in t or "get content" in t or "read page" in t:
            if url:
                return self.fetch(url)
            return CommandResult(False, "Please provide a URL to fetch")

        # Open in browser
        if "open" in t or "go to" in t or "visit" in t or "browse" in t:
            if url:
                return self.open_url(url)
            return CommandResult(False, "Please provide a URL to open")

        # Search
        if "search" in t or "google" in t:
            # Extract search query
            search_match = re.search(r"(?:search|google)\s+(?:for\s+)?(.+)", text, re.IGNORECASE)
            if search_match:
                query = search_match.group(1).strip()
                return self.search(query)
            return CommandResult(False, "What would you like to search for?")

        # Just a URL was provided
        if url:
            return self.fetch(url)

        return CommandResult(False, f"Unknown web command: {text}")
