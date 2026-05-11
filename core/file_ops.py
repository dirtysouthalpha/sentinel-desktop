"""Safe file operations."""
import os
import logging

logger = logging.getLogger(__name__)


def read_file(path: str, encoding: str = "utf-8"):
    """Read file contents. Returns string or None on error."""
    try:
        with open(path, "r", encoding=encoding) as f:
            return f.read()
    except Exception as e:
        logger.error("read_file(%s) failed: %s", path, e)
        return None


def write_file(path: str, content: str, encoding: str = "utf-8") -> bool:
    """Write file contents. Creates parent dirs. Returns True on success."""
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding=encoding) as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error("write_file(%s) failed: %s", path, e)
        return False


def list_directory(path: str = "."):
    """List directory contents. Returns list of dicts or None."""
    try:
        entries = []
        for entry in os.scandir(path):
            entries.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else 0,
            })
        return sorted(entries, key=lambda e: (not e["is_dir"], e["name"].lower()))
    except Exception as e:
        logger.error("list_directory(%s) failed: %s", path, e)
        return None
