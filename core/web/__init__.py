"""Web automation module — browser control, recording, and replay."""

from .browser import BrowserController, ElementInfo, PageInfo
from .recorder import RecordedAction, Recording, BrowserRecorder, BrowserReplayer

__all__ = [
    "BrowserController", "ElementInfo", "PageInfo",
    "RecordedAction", "Recording", "BrowserRecorder", "BrowserReplayer",
]
