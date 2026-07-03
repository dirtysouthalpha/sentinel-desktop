"""Web automation module — browser control, recording, and replay."""

from .browser import BrowserController, ElementInfo, PageInfo
from .recorder import BrowserRecorder, BrowserReplayer, RecordedAction, Recording

__all__ = [
    "BrowserController",
    "ElementInfo",
    "PageInfo",
    "RecordedAction",
    "Recording",
    "BrowserRecorder",
    "BrowserReplayer",
]
