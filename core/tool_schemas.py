"""Sentinel Desktop v3 — Tool/function schemas for LLM tool-calling.

OpenAI and Anthropic both support structured tool calls; using them is far
more reliable than asking the model to return JSON-as-text and regexing it
out of the response. LLMClient converts these OpenAI-style definitions to
Anthropic's native shape automatically.
"""

from __future__ import annotations

from typing import Any

# Each tool maps 1:1 to a key in ActionExecutor._dispatch_table.
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click at screen coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X pixel"},
                    "y": {"type": "integer", "description": "Y pixel"},
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "default": "left",
                    },
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "double_click",
            "description": "Double-click at screen coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X pixel"},
                    "y": {"type": "integer", "description": "Y pixel"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "right_click",
            "description": "Right-click at screen coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X pixel"},
                    "y": {"type": "integer", "description": "Y pixel"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type a string at the current cursor focus.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press a single key (enter, tab, escape, etc.).",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hotkey",
            "description": "Press a key combination, e.g. ['ctrl','c'].",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                },
                "required": ["keys"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll the wheel by N ticks (positive=up, negative=down).",
            "parameters": {
                "type": "object",
                "properties": {"amount": {"type": "integer"}},
                "required": ["amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "Capture a fresh screenshot.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_image",
            "description": "Find a template image on the screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_path": {"type": "string"},
                    "confidence": {"type": "number", "default": 0.8},
                },
                "required": ["template_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_text",
            "description": (
                "Locate visible text on screen via OCR and click its centre. "
                "Preferred over click(x,y) when you can name the text — much "
                "more reliable than guessing coordinates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Visible text to click on, e.g. 'Send', 'File menu'.",
                    },
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "default": "left",
                    },
                    "fuzzy": {"type": "boolean", "default": True},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_text",
            "description": (
                "OCR text from the screen. By default reads only the "
                "FOCUSED window (much more useful than full-screen OCR on "
                "multi-monitor setups). Pass scope='all' to OCR everything, "
                "or window='<title>' to target a specific window."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["focused", "all"], "default": "focused"},
                    "window": {
                        "type": "string",
                        "description": (
                            "Partial window title to target instead of the focused window."
                        ),
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_window",
            "description": (
                "OCR a specific window by partial title match. Returns the text content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Partial window title, e.g. 'Outlook' or 'Mail'.",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait N seconds.",
            "parameters": {
                "type": "object",
                "properties": {"seconds": {"type": "number"}},
                "required": ["seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "smart_open",
            "description": (
                "PREFERRED way to open or switch to an app. Focuses the "
                "existing window if it's already running, else launches it. "
                "Works with friendly names: outlook, chrome, edge, excel, "
                "word, teams, slack, notepad, vscode, explorer, calc, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "App name e.g. 'outlook'"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": (
                "Start a raw program by absolute path. "
                "Prefer smart_open() unless you really need a specific exe."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "focus_window",
            "description": "Bring a window to the foreground by partial title match.",
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_window",
            "description": "Close a window by partial title match.",
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_windows",
            "description": "List all visible windows.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_controls",
            "description": (
                "Enumerate accessible controls in a window (buttons, edits, "
                "menu items, etc.) with their names and screen positions. "
                "Use this to find the right control_name before click_control."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "window_title": {
                        "type": "string",
                        "description": "Partial window title. Omit for the foreground window.",
                    },
                    "max_results": {"type": "integer", "default": 60},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_control",
            "description": (
                "Click a native Windows control by its accessibility name, "
                "automation_id, or control_type. Far more reliable than "
                "click(x,y) when the target has a visible label."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Visible label or accessible name, e.g. 'Send', 'OK'.",
                    },
                    "automation_id": {"type": "string"},
                    "control_type": {
                        "type": "string",
                        "description": "e.g. 'ButtonControl', 'EditControl', 'MenuItemControl'.",
                    },
                    "window_title": {"type": "string"},
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "default": "left",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_text",
            "description": (
                "Set the value of an editable control (Edit / TextBox / "
                "ComboBox) by its accessibility name. Doesn't fire keystrokes "
                "when the control supports the ValuePattern."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "name": {
                        "type": "string",
                        "description": "Label of the edit, e.g. 'Subject', 'Search'.",
                    },
                    "automation_id": {"type": "string"},
                    "window_title": {"type": "string"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a text file (creates parent directories).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_read",
            "description": "Read text from the system clipboard.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_write",
            "description": "Write text to the system clipboard.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "note",
            "description": "Make a note to yourself (no side effects).",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Signal task completion with a summary of what was done.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drag",
            "description": "Drag from one point to another.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_x": {"type": "integer", "description": "Start X pixel"},
                    "from_y": {"type": "integer", "description": "Start Y pixel"},
                    "to_x": {"type": "integer", "description": "End X pixel"},
                    "to_y": {"type": "integer", "description": "End Y pixel"},
                    "duration": {
                        "type": "number",
                        "default": 0.5,
                        "description": "Drag duration in seconds",
                    },
                    "button": {"type": "string", "enum": ["left", "right"], "default": "left"},
                },
                "required": ["from_x", "from_y", "to_x", "to_y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "smart_wait",
            "description": "Wait until the screen changes (visual diff). Faster than fixed wait.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeout": {
                        "type": "number",
                        "default": 10,
                        "description": "Max wait in seconds",
                    },
                    "region": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional [x, y, w, h] region to watch",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait_for_stable",
            "description": "Wait until the screen stops changing (e.g. page load complete).",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeout": {"type": "number", "default": 10},
                    "stable_time": {
                        "type": "number",
                        "default": 1.5,
                        "description": "Seconds of no change",
                    },
                    "region": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional [x, y, w, h] region to watch",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait_for_text",
            "description": "Wait until specific text appears on screen via OCR.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to wait for"},
                    "timeout": {"type": "number", "default": 10},
                    "region": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional [x, y, w, h] region to watch",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait_for_image",
            "description": "Wait for a template image to appear on screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_path": {"type": "string"},
                    "timeout": {"type": "integer", "default": 30},
                    "confidence": {"type": "number", "default": 0.8},
                },
                "required": ["template_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "system_info",
            "description": "Get system details (OS, resolution, memory, etc.).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_processes",
            "description": "List running processes.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_process",
            "description": "Start a process by path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process",
            "description": "Kill a process by PID or name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {"type": "integer"},
                    "name": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "powershell",
            "description": "Run a PowerShell command and return output.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_script",
            "description": "Replay a recorded script from a JSON file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_app",
            "description": "Close an app by name or PID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "pid": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List directory contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                },
            },
        },
    },
    # ── Web / Browser actions (v8.0 — Playwright) ─────────────────────────
    {
        "type": "function",
        "function": {
            "name": "web_open",
            "description": (
                "Open a URL in the embedded browser. Use for web app automation — "
                "firewalls, routers, admin portals, dashboards."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"},
                    "wait_until": {
                        "type": "string",
                        "enum": ["load", "domcontentloaded", "networkidle", "commit"],
                        "default": "load",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_click",
            "description": (
                "Click an element in the browser by CSS selector, visible text, "
                "or ARIA role. Auto-scrolls into view."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector, e.g. '#login-btn'"},
                    "text": {"type": "string", "description": "Visible text to click"},
                    "role": {"type": "string", "description": "ARIA role, e.g. 'button', 'link'"},
                    "name": {"type": "string", "description": "Accessible name (use with role)"},
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "default": "left",
                    },
                    "click_count": {"type": "integer", "default": 1},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_type",
            "description": (
                "Type text into a browser form field. Clears existing content by default. "
                "Find field by CSS selector, label text, or ARIA role."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                    "selector": {"type": "string", "description": "CSS selector for the input"},
                    "label": {"type": "string", "description": "Label text associated with input"},
                    "role": {"type": "string", "description": "ARIA role, e.g. 'textbox'"},
                    "name": {"type": "string", "description": "Accessible name"},
                    "clear": {"type": "boolean", "default": True},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_read",
            "description": (
                "Read text content from the browser page. Pass a selector to read "
                "a specific element, or omit for the full page."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector (omit for full page)"},
                    "full_page": {"type": "boolean", "default": False},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_extract",
            "description": (
                "Extract structured data from the browser page. Defaults to HTML tables "
                "→ JSON. Also works with lists and other elements."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "default": "table",
                        "description": "CSS selector for the data container",
                    },
                    "format": {"type": "string", "enum": ["json", "text"], "default": "json"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_wait_for",
            "description": "Wait for an element, text, or network idle in the browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector to wait for"},
                    "text": {"type": "string", "description": "Text to wait for on the page"},
                    "state": {
                        "type": "string",
                        "enum": ["visible", "hidden", "attached", "detached"],
                        "default": "visible",
                    },
                    "timeout": {"type": "number", "default": 30, "description": "Max wait in seconds"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_screenshot",
            "description": "Capture a screenshot of the browser viewport or element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector (omit for viewport)"},
                    "full_page": {"type": "boolean", "default": False},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_eval_js",
            "description": "Execute JavaScript in the browser context and return the result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "JavaScript expression"},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_download",
            "description": "Download a file from the browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to download"},
                    "save_path": {"type": "string", "description": "Local path to save file"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_upload",
            "description": "Upload files to a web form via a file input element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the file input",
                    },
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Paths of files to upload",
                    },
                },
                "required": ["selector", "file_paths"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_tabs",
            "description": "Manage browser tabs — list, switch, create, or close.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_action": {
                        "type": "string",
                        "enum": ["list", "switch", "new", "close"],
                        "default": "list",
                    },
                    "index": {"type": "integer", "description": "Tab index for switch/close"},
                    "url": {"type": "string", "description": "URL for new tab"},
                },
            },
        },
    },
    # ── Netops / SSH actions (v9.0 — network device control) ────────────
    {
        "type": "function",
        "function": {
            "name": "ssh_connect",
            "description": (
                "Connect to a network device (router, switch, firewall) via SSH. "
                "Must connect before running any ssh_run/ssh_show/ssh_ping commands."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hostname": {"type": "string", "description": "Device IP or hostname"},
                    "username": {"type": "string", "description": "SSH username"},
                    "password": {"type": "string", "description": "SSH password"},
                    "port": {"type": "integer", "default": 22},
                    "key_filename": {"type": "string", "description": "Path to SSH private key"},
                },
                "required": ["hostname"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_disconnect",
            "description": "Disconnect from an SSH device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hostname": {"type": "string", "description": "Device to disconnect from"},
                },
                "required": ["hostname"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_run",
            "description": "Run a raw command on a connected SSH device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hostname": {"type": "string", "description": "Connected device hostname"},
                    "command": {"type": "string", "description": "Command to execute"},
                    "timeout": {"type": "number", "default": 30},
                },
                "required": ["hostname", "command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_show",
            "description": (
                "Run a device-aware show command. Knows syntax for Cisco IOS, "
                "JunOS, FortiGate, MikroTik, pfSense, Linux. "
                "Options: version, interfaces, routing, arp, cpu, logging, config"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hostname": {"type": "string", "description": "Connected device"},
                    "what": {
                        "type": "string",
                        "enum": ["version", "interfaces", "routing", "arp", "cpu", "logging", "config"],
                    },
                    "device_type": {
                        "type": "string",
                        "default": "generic",
                        "description": "cisco_ios, cisco_nxos, juniper_junos, fortigate, mikrotik, pfsense, linux, generic",
                    },
                },
                "required": ["hostname", "what"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_ping",
            "description": "Ping a target from a connected network device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hostname": {"type": "string", "description": "Connected device"},
                    "target": {"type": "string", "description": "IP or hostname to ping"},
                    "count": {"type": "integer", "default": 4},
                    "device_type": {"type": "string", "default": "generic"},
                },
                "required": ["hostname", "target"],
            },
        },
    },
]


# Providers known to support OpenAI/Anthropic tool calling. Other OpenAI-
# compatible providers technically accept the `tools` parameter but model
# support varies wildly, so we keep this conservative.
TOOL_CAPABLE_PROVIDERS = {
    "openai",
    "anthropic",
    "google",
    "groq",
    "mistral",
    "openrouter",
    "fireworks",
    "together",
    "cerebras",
    "minimax",
    "moonshot",
    "qwen",
    "cohere",
    "nvidia",
    "huggingface",
    "github",
    "deepinfra",
    "zai",
    "deepseek",
}
