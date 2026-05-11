<div align="center">

# ⬡ Sentinel Desktop v2

**AI-powered Windows desktop automation agent.**

Give it a goal in plain English. It sees your screen, moves the mouse, types, and interacts with any application — autonomously.

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## Features

- 🤖 **Vision-driven agent loop** — screenshots → LLM → action → verify → repeat
- 🖱️ **Full desktop control** — mouse, keyboard, clipboard, file I/O
- 🪟 **Window management** — focus, close, list, resize windows
- 📸 **Screen analysis** — template matching, OCR-ready screenshots
- 🔌 **16+ LLM providers** — OpenAI, Anthropic, Google, Azure, Ollama, LM Studio, and more
- 🌐 **Three modes** — GUI, headless API, CLI
- 🔒 **MSP-grade safety** — approval mode, sensitive field protection, tenant lockdown
- 📝 **Forensic logging** — every action logged with timestamps
- 🎨 **Dark theme** — customtkinter with midnight/ocean/ember themes
- 📡 **WebSocket live feed** — real-time status updates

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run GUI mode
python main.py

# Run headless API server
python main.py --api --port 8091

# Run single command
python main.py -c "Open Notepad and type Hello World"
```

Or on Windows: double-click `install_and_run.bat`

## Configuration

First run opens settings. Configure:
1. **Provider** — Choose your LLM provider (OpenAI, Anthropic, etc.)
2. **API Key** — Paste your key
3. **Model** — Enter model name or auto-detect
4. **Step Budget** — Max actions per goal (default: 100)

Config stored at:
- Windows: `%APPDATA%\SentinelDesktop\config.json`
- Linux/Mac: `~/.sentinel-desktop/config.json`

## API Reference

When running in `--api` mode:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/goal` | Start agent with a goal |
| POST | `/command` | Execute single action |
| POST | `/stop` | Stop running agent |
| GET | `/screenshot` | Capture screen as base64 PNG |
| GET | `/status` | Agent status |
| GET | `/windows` | List visible windows |
| GET | `/processes` | List running processes |
| GET | `/system` | System info |
| GET | `/config` | Read config |
| PUT | `/config` | Update config |
| GET | `/log` | Forensic run log |
| WS | `/ws` | Live status feed |

### Examples

```bash
# Start a goal
curl -X POST http://localhost:8091/goal \
  -H "Content-Type: application/json" \
  -d '{"goal": "Open Chrome and navigate to github.com"}'

# Take a screenshot
curl http://localhost:8091/screenshot

# Execute a direct action
curl -X POST http://localhost:8091/command \
  -d '{"command": "{\"action\":\"click\",\"x\":500,\"y\":300}"}'
```

## Supported Actions

The agent can perform these actions:

| Action | Description |
|--------|-------------|
| `click` | Click at screen coordinates |
| `click_image` | Find and click a template image |
| `type_text` | Type text character by character |
| `press_key` | Press a single key |
| `hotkey` | Press key combination |
| `scroll` | Scroll up or down |
| `screenshot` | Take a fresh screenshot |
| `find_image` | Find image on screen |
| `wait_for_image` | Wait for image to appear |
| `wait` | Wait N seconds |
| `open_app` | Start a program |
| `focus_window` | Bring window to front |
| `close_window` | Close a window |
| `list_windows` | List all visible windows |
| `read_file` | Read a text file |
| `write_file` | Write a text file |
| `list_directory` | List directory contents |
| `clipboard_read` | Read clipboard |
| `clipboard_write` | Write to clipboard |
| `system_info` | Get system details |
| `list_processes` | List running processes |
| `kill_process` | Kill a process |
| `note` | Make a note (no side effects) |
| `finish` | Signal task completion |

## Architecture

```
sentinel-desktop/
├── main.py              # Entry point (GUI / API / CLI modes)
├── config.py            # Settings persistence
├── core/
│   ├── engine.py        # Agent loop (screenshot → LLM → action → verify)
│   ├── action_executor.py  # Dispatches actions to desktop control
│   ├── llm_client.py    # Multi-provider LLM client
│   ├── provider_registry.py  # Provider catalog (16+ providers)
│   ├── desktop.py       # Mouse, keyboard, screen control
│   ├── screenshot.py    # Screen capture + template matching
│   ├── window_manager.py   # Window management
│   ├── process_manager.py  # Process management
│   ├── clipboard.py     # Clipboard read/write
│   ├── file_ops.py      # Safe file operations
│   └── system_info.py   # System information
├── api/
│   └── server.py        # FastAPI headless control server
├── gui/
│   ├── app.py           # Main GUI window
│   └── themes.py        # Dark theme definitions
└── requirements.txt
```

## Safety

- **Approval mode**: Every action requires user confirmation before execution
- **Sensitive field protection**: Won't type into password/credential fields
- **Tenant lockdown**: Restrict file access to tenant-scoped paths
- **Failsafe**: Move mouse to screen corner to abort (pyautogui built-in)
- **Step budget**: Agent stops after N actions (configurable, default 100)
- **Forensic log**: Every action logged with timestamp, params, and result

## Companion Projects

- **[Sentinel Override](https://github.com/dirtysouthalpha/sentinel-override)** — Browser automation agent (Chrome extension)
- **[Sentinel MCP](https://github.com/dirtysouthalpha/sentinel-mcp-server)** — Model Context Protocol server

## License

MIT
