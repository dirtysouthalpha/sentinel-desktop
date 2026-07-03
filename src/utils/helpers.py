"""Miscellaneous helper functions."""
import platform
from pathlib import Path

def is_windows():
    return platform.system() == "Windows"

def is_linux():
    return platform.system() == "Linux"

def get_os_name():
    return platform.system()

def format_bytes(n):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"

def parse_coords(text: str):
    import re
    match = re.search(r'(\d+)\s*[,x]\s*(\d+)', text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None
