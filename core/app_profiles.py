"""
Sentinel Desktop v2 — Application profiles.

Pre-configured strategies for common desktop applications. Each profile tells
the agent the best approach for interacting with a specific app — which UIA
control types to target, whether stealth input works, known menu paths, and
timing adjustments.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AppProfile:
    """Strategy profile for a specific desktop application."""

    name: str
    display_name: str
    window_title_patterns: list[str]
    stealth_compatible: str = "partial"  # "full", "partial", "none"
    preferred_input: str = "uia"  # "uia", "postmessage", "physical"
    timing: dict[str, float] = field(
        default_factory=lambda: {
            "launch_delay": 2.0,
            "action_delay": 0.3,
            "page_load_delay": 2.0,
        }
    )
    known_controls: dict[str, str] = field(default_factory=dict)
    menu_paths: dict[str, list[str]] = field(default_factory=dict)
    quirks: list[str] = field(default_factory=list)
    strategies: dict[str, str] = field(default_factory=dict)


PROFILES: dict[str, AppProfile] = {
    "chrome": AppProfile(
        name="chrome",
        display_name="Google Chrome",
        window_title_patterns=["Chrome", "Google Chrome"],
        stealth_compatible="partial",
        preferred_input="uia",
        timing={"launch_delay": 3.0, "action_delay": 0.3, "page_load_delay": 3.0},
        known_controls={
            "address_bar": "Address and search bar",
            "new_tab": "New Tab",
            "menu": "Customize and control Google Chrome",
        },
        menu_paths={
            "new_tab": ["File", "New Tab"],
            "close_tab": ["File", "Close Tab"],
            "save_page": ["File", "Save page as..."],
            "print": ["File", "Print..."],
            "settings": ["Customize and control Google Chrome", "Settings"],
            "dev_tools": ["More tools", "Developer Tools"],
        },
        quirks=[
            "Ignores PostMessage clicks on web content (Chromium renderer)",
            "Address bar requires physical click or Ctrl+L",
            "Tabs can be targeted by name via UIA",
        ],
        strategies={
            "navigate": "Click address bar (Ctrl+L) then type URL",
            "click_link": "Use coordinates from screenshot, not UIA",
            "read_page": "Use Ctrl+A then Ctrl+C to get page text",
        },
    ),
    "edge": AppProfile(
        name="edge",
        display_name="Microsoft Edge",
        window_title_patterns=["Edge", "Microsoft Edge"],
        stealth_compatible="partial",
        preferred_input="uia",
        timing={"launch_delay": 3.0, "action_delay": 0.3, "page_load_delay": 3.0},
        known_controls={
            "address_bar": "Address and search bar",
            "new_tab": "New Tab",
            "menu": "Settings and more",
        },
        menu_paths={
            "new_tab": ["File", "New Tab"],
            "settings": ["Settings and more", "Settings"],
        },
        quirks=["Same Chromium limitations as Chrome"],
        strategies={"navigate": "Ctrl+L then type URL"},
    ),
    "firefox": AppProfile(
        name="firefox",
        display_name="Mozilla Firefox",
        window_title_patterns=["Firefox", "Mozilla Firefox"],
        stealth_compatible="partial",
        preferred_input="uia",
        timing={"launch_delay": 3.0, "action_delay": 0.3, "page_load_delay": 3.0},
        known_controls={"address_bar": "Search with Google or enter address"},
        quirks=["Different UIA tree structure than Chromium browsers"],
        strategies={"navigate": "Ctrl+L then type URL"},
    ),
    "excel": AppProfile(
        name="excel",
        display_name="Microsoft Excel",
        window_title_patterns=["Excel", "Microsoft Excel"],
        stealth_compatible="full",
        preferred_input="uia",
        timing={"launch_delay": 4.0, "action_delay": 0.2, "page_load_delay": 2.0},
        known_controls={
            "cell": "Grid",
            "formula_bar": "Formula Bar",
            "ribbon": "Ribbon",
            "sheet_tab": "Sheet Tab Bar",
        },
        menu_paths={
            "save": ["File", "Save"],
            "save_as": ["File", "Save As"],
            "open": ["File", "Open"],
            "new": ["File", "New"],
            "print": ["File", "Print"],
            "insert_row": ["Home", "Insert", "Insert Sheet Rows"],
            "sort": ["Data", "Sort"],
            "filter": ["Data", "Filter"],
        },
        quirks=["Cell editing requires physical F2 or double-click"],
        strategies={
            "edit_cell": "Click cell, press F2, type, press Enter",
            "read_cell": "Click cell, read formula bar value",
            "copy_range": "Select range via Shift+click, Ctrl+C",
        },
    ),
    "word": AppProfile(
        name="word",
        display_name="Microsoft Word",
        window_title_patterns=["Word", "Microsoft Word"],
        stealth_compatible="full",
        preferred_input="uia",
        timing={"launch_delay": 4.0, "action_delay": 0.2, "page_load_delay": 2.0},
        known_controls={"document": "Document", "ribbon": "Ribbon"},
        menu_paths={
            "save": ["File", "Save"],
            "save_as": ["File", "Save As"],
            "print": ["File", "Print"],
        },
        quirks=["Document body accepts PostMessage typing well"],
        strategies={"type_text": "Click position in document, then type_text"},
    ),
    "outlook": AppProfile(
        name="outlook",
        display_name="Microsoft Outlook",
        window_title_patterns=["Outlook", "Microsoft Outlook"],
        stealth_compatible="full",
        preferred_input="uia",
        timing={"launch_delay": 5.0, "action_delay": 0.5, "page_load_delay": 3.0},
        known_controls={
            "mail_list": "Mail List",
            "reading_pane": "Reading Pane",
            "folder_tree": "Folder Tree",
            "search": "Search Mail",
        },
        menu_paths={
            "new_email": ["Home", "New Email"],
            "reply": ["Home", "Reply"],
            "reply_all": ["Home", "Reply All"],
            "forward": ["Home", "Forward"],
        },
        quirks=["Loading inbox can take 5+ seconds on first open"],
        strategies={
            "read_email": "Click email in list, wait for reading pane",
            "send_email": "New Email → fill fields → Send",
        },
    ),
    "notepad": AppProfile(
        name="notepad",
        display_name="Notepad",
        window_title_patterns=["Notepad", "Untitled - Notepad"],
        stealth_compatible="full",
        preferred_input="postmessage",
        timing={"launch_delay": 1.0, "action_delay": 0.1, "page_load_delay": 0.5},
        menu_paths={
            "save": ["File", "Save"],
            "save_as": ["File", "Save As"],
            "open": ["File", "Open"],
        },
        quirks=["Simple app, all input methods work perfectly"],
    ),
    "vscode": AppProfile(
        name="vscode",
        display_name="Visual Studio Code",
        window_title_patterns=["Visual Studio Code", "VS Code"],
        stealth_compatible="partial",
        preferred_input="physical",
        timing={"launch_delay": 4.0, "action_delay": 0.3, "page_load_delay": 3.0},
        known_controls={
            "editor": "Text Editor",
            "terminal": "Terminal",
            "explorer": "Explorer",
            "search": "Search",
        },
        menu_paths={
            "open_file": ["File", "Open File..."],
            "save": ["File", "Save"],
            "command_palette": ["View", "Command Palette..."],
            "terminal": ["Terminal", "New Terminal"],
        },
        quirks=[
            "Electron-based — PostMessage unreliable",
            "Use keyboard shortcuts heavily (Ctrl+P, Ctrl+Shift+P)",
        ],
        strategies={
            "open_file": "Ctrl+P, type filename",
            "run_command": "Ctrl+Shift+P, type command",
        },
    ),
    "live2d_cubism": AppProfile(
        name="live2d_cubism",
        display_name="Live2D Cubism Editor",
        window_title_patterns=["Cubism", "Live2D"],
        stealth_compatible="none",
        preferred_input="physical",
        timing={"launch_delay": 5.0, "action_delay": 0.5, "page_load_delay": 3.0},
        menu_paths={
            "export_runtime": ["File", "Export for Runtime", "Export for Runtime"],
            "export_moc3": ["File", "Export for Runtime"],
            "open_project": ["File", "Open..."],
            "save_project": ["File", "Save"],
            "texture_atlas": ["Texture Atlas", "Add Texture"],
        },
        quirks=[
            "Canvas ignores ALL PostMessage and UIA — physical mouse only",
            "Export dialogs require precise menu navigation",
            "Free tier: 30 parameters, 100 art meshes max",
            "Model is .cmo3 project, runtime export creates .moc3 + textures + .model3.json",
        ],
        strategies={
            "export_runtime": (
                "Physical click File → wait → click Export for Runtime → wait → "
                "click Export for Runtime in submenu → wait for dialog → click OK"
            ),
            "rig_parameter": (
                "Click parameter in list → click Add Parameter → drag mesh points on canvas"
            ),
        },
    ),
    "file_explorer": AppProfile(
        name="file_explorer",
        display_name="File Explorer",
        window_title_patterns=["File Explorer", "Windows Explorer", "Explorer"],
        stealth_compatible="full",
        preferred_input="uia",
        timing={"launch_delay": 1.5, "action_delay": 0.2, "page_load_delay": 1.0},
        known_controls={
            "address_bar": "Address Band",
            "navigation": "Navigation Pane",
            "file_list": "Items View",
            "search": "Search Box",
        },
        menu_paths={
            "new_folder": ["New", "Folder"],
            "copy": ["Copy"],
            "paste": ["Paste"],
            "delete": ["Delete"],
        },
        quirks=["UIA works well for navigation and file operations"],
        strategies={"navigate": "Click address bar, type path, Enter"},
    ),
    "teams": AppProfile(
        name="teams",
        display_name="Microsoft Teams",
        window_title_patterns=["Teams", "Microsoft Teams"],
        stealth_compatible="partial",
        preferred_input="physical",
        timing={"launch_delay": 5.0, "action_delay": 0.5, "page_load_delay": 4.0},
        quirks=[
            "Electron-based — limited stealth",
            "Heavy animations — wait longer between actions",
        ],
    ),
    "cmd": AppProfile(
        name="cmd",
        display_name="Command Prompt",
        window_title_patterns=["Command Prompt", "cmd.exe"],
        stealth_compatible="full",
        preferred_input="postmessage",
        timing={"launch_delay": 1.0, "action_delay": 0.3, "page_load_delay": 0.5},
        quirks=["Accepts all input methods perfectly"],
        strategies={"run_command": "Type command, press Enter"},
    ),
    "powershell": AppProfile(
        name="powershell",
        display_name="PowerShell",
        window_title_patterns=["PowerShell", "pwsh"],
        stealth_compatible="full",
        preferred_input="postmessage",
        timing={"launch_delay": 1.5, "action_delay": 0.3, "page_load_delay": 0.5},
        quirks=["Accepts all input methods perfectly"],
        strategies={"run_command": "Type command, press Enter"},
    ),
    "task_manager": AppProfile(
        name="task_manager",
        display_name="Task Manager",
        window_title_patterns=["Task Manager"],
        stealth_compatible="none",
        preferred_input="physical",
        timing={"launch_delay": 2.0, "action_delay": 0.3, "page_load_delay": 1.5},
        quirks=["Runs as admin — limited automation access"],
        strategies={"kill_process": "Click process in list, press Delete key"},
    ),
    "settings": AppProfile(
        name="settings",
        display_name="Windows Settings",
        window_title_patterns=["Settings"],
        stealth_compatible="full",
        preferred_input="uia",
        timing={"launch_delay": 2.0, "action_delay": 0.3, "page_load_delay": 1.5},
        known_controls={"search": "Find a setting"},
        strategies={"find_setting": "Type in search box, click result"},
    ),
}


def detect_profile(window_title: str) -> AppProfile | None:
    """Match a window title to the best app profile."""
    if not window_title:
        return None
    title_lower = window_title.lower()
    for profile in PROFILES.values():
        for pattern in profile.window_title_patterns:
            if pattern.lower() in title_lower:
                return profile
    return None


def get_profile(name: str) -> AppProfile | None:
    """Get a profile by name."""
    return PROFILES.get(name)


def list_profiles() -> list[AppProfile]:
    """Return all profiles."""
    return list(PROFILES.values())


def get_timing_for_app(window_title: str) -> dict[str, float]:
    """Convenience: get timing defaults for the app matching the window title."""
    profile = detect_profile(window_title)
    if profile:
        return profile.timing
    return {"launch_delay": 2.0, "action_delay": 0.3, "page_load_delay": 2.0}
