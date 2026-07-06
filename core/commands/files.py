"""
File Operation Commands
List, search, read files.
"""
import os
import glob
from pathlib import Path
from core.legacy_engine import CommandResult


class FileCommands:
    """File system operations."""

    def execute(self, text: str) -> CommandResult:
        text_lower = text.lower().strip()

        if text_lower.startswith("list ") or text_lower.startswith("dir ") or text_lower.startswith("ls"):
            path = text.split(None, 1)[1] if len(text.split()) > 1 else os.getcwd()
            return self.list_files(path)

        if text_lower.startswith("find ") or text_lower.startswith("search file"):
            query = text.split(None, 1)[1] if len(text.split()) > 1 else ""
            return self.find_files(query, os.getcwd())

        if text_lower.startswith("read "):
            path = text[5:].strip()
            return self.read_file(path)

        return CommandResult(False, f"Unknown file command: {text}")

    def list_files(self, path: str) -> CommandResult:
        try:
            p = Path(path).expanduser()
            if not p.exists():
                return CommandResult(False, f"Path not found: {path}")
            if not p.is_dir():
                return CommandResult(False, f"Not a directory: {path}")

            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            lines = []
            for entry in entries[:50]:
                if entry.is_dir():
                    lines.append(f"  [DIR]  {entry.name}/")
                else:
                    size = entry.stat().st_size
                    size_str = f"{size/1024:.1f}KB" if size < 1024*1024 else f"{size/(1024*1024):.1f}MB"
                    lines.append(f"  [FILE] {entry.name} ({size_str})")

            msg = f"Listing: {p}\n" + "\n".join(lines)
            if len(entries) > 50:
                msg += f"\n... and {len(entries) - 50} more"
            return CommandResult(True, msg)
        except Exception as e:
            return CommandResult(False, f"List failed: {e}")

    def find_files(self, pattern: str, search_path: str) -> CommandResult:
        try:
            results = []
            p = Path(search_path).expanduser()
            for item in p.rglob(f"*{pattern}*"):
                if len(results) >= 20:
                    break
                try:
                    rel = item.relative_to(p)
                    results.append(str(rel))
                except ValueError:
                    results.append(str(item))

            if results:
                return CommandResult(True, f"Found {len(results)} match(es):\n" + "\n".join(results[:20]))
            return CommandResult(True, f"No files matching '{pattern}' found in {search_path}")
        except Exception as e:
            return CommandResult(False, f"Search failed: {e}")

    def read_file(self, path: str) -> CommandResult:
        try:
            p = Path(path).expanduser()
            if not p.exists():
                return CommandResult(False, f"File not found: {path}")
            if p.stat().st_size > 100_000:
                return CommandResult(False, "File too large (>100KB). Use a text editor.")
            content = p.read_text(errors="replace")
            preview = content[:2000]
            if len(content) > 2000:
                preview += f"\n... ({len(content)} chars total, showing first 2000)"
            return CommandResult(True, f"=== {p.name} ===\n{preview}")
        except Exception as e:
            return CommandResult(False, f"Read failed: {e}")
