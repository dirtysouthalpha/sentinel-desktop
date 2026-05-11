"""
Sentinel Desktop v2 — Tool/function schemas for LLM tool-calling.

OpenAI and Anthropic both support structured tool calls; using them is far
more reliable than asking the model to return JSON-as-text and regexing it
out of the response. LLMClient converts these OpenAI-style definitions to
Anthropic's native shape automatically.
"""

from __future__ import annotations

from typing import Any, Dict, List


# Each tool maps 1:1 to a key in ActionExecutor._dispatch_table.
TOOLS: List[Dict[str, Any]] = [
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
                    "text": {"type": "string", "description": "Visible text to click on, e.g. 'Send', 'File menu'."},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
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
                    "window": {"type": "string", "description": "Partial window title to target instead of the focused window."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_window",
            "description": "OCR a specific window by partial title match. Returns the text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Partial window title, e.g. 'Outlook' or 'Mail'."},
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
            "description": "Start a raw program by absolute path. Prefer smart_open() unless you really need a specific exe.",
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
                    "window_title": {"type": "string", "description": "Partial window title. Omit for the foreground window."},
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
                    "name": {"type": "string", "description": "Visible label or accessible name, e.g. 'Send', 'OK'."},
                    "automation_id": {"type": "string"},
                    "control_type": {"type": "string", "description": "e.g. 'ButtonControl', 'EditControl', 'MenuItemControl'."},
                    "window_title": {"type": "string"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
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
                    "name": {"type": "string", "description": "Label of the edit, e.g. 'Subject', 'Search'."},
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
]


# Providers known to support OpenAI/Anthropic tool calling. Other OpenAI-
# compatible providers technically accept the `tools` parameter but model
# support varies wildly, so we keep this conservative.
TOOL_CAPABLE_PROVIDERS = {
    "openai", "anthropic", "google", "groq", "mistral", "openrouter",
    "fireworks", "together", "cerebras",
    "minimax", "moonshot", "qwen", "cohere", "nvidia",
    "huggingface", "github", "deepinfra", "zai", "deepseek",
}
