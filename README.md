<div align="center">

# ⬡ Sentinel Desktop v17.0

**AI-powered desktop automation agent — cross-platform, cyberpunk HUD edition.**

Give it a goal in plain English. It sees your screen, moves the mouse, types, and interacts with any application — autonomously.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Version](https://img.shields.io/badge/version-17.0.0-orange)](https://github.com/dirtysouthalpha/sentinel-desktop/releases)
[![Tests](https://img.shields.io/badge/tests-7823%20passing-brightgreen)](https://github.com/dirtysouthalpha/sentinel-desktop/actions)
[![Lint](https://img.shields.io/badge/lint-0%20errors-brightgreen)](https://github.com/dirtysouthalpha/sentinel-desktop/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

105+ action types · 7,823 tests · 35+ API endpoints · 20+ LLM providers · MCP server · Fleet/daemon mode

</div>

---

<div align="center">

### 🧠 Neuralis Brain — One mind across your whole fleet

</div>

Sentinel doesn't just automate — **it learns.** Every task it runs, every fix it lands, every tricky issue it solves gets distilled into the **Neuralis Brain** — a shared memory that *every* agent in your fleet reads from and writes to.

**The brain learns from all clients and gets better and better with every task.**

- 🔁 **Cross-agent memory** — Sentinel Desktop, Claude Code, opencode, and every other tool in the fleet share one brain. A fix Sentinel finds on a server at 2am is knowledge Claude Code can recall at noon.
- 📈 **Gets smarter over time** — the more tasks it runs, the more context the brain holds. Hard-won solutions to advanced technical issues (server configs, stubborn drivers, network edge cases) are never solved twice.
- 🖥️ **Built for the field** — engineered for IT work on servers and workstations. Sentinel captures the *goal → actions → outcome* of each engagement and feeds the durable lessons back in.
- 🔌 **Direct bridge** — Sentinel speaks to the brain over HTTP (`NEURALIS_BRAIN_URL`), no extra processes. Seven operations: `think`, `recall`, `search`, `context`, `opinions`, `fire`, `stats`.

> **Status:** arriving in **v18.0**. The bridge is the foundation — automatic recall-at-task-start and a full consolidation loop land in the phases that follow. Track progress in [CLAUDE.md](CLAUDE.md).

---

## Features

- 🤖 **Vision-driven agent loop** — screenshots → LLM → action → verify → repeat
- 🖱️ **Full desktop control** — mouse, keyboard, clipboard, file I/O, multi-monitor screenshots
- 👁️ **OCR-aware** — `click_text` and `read_text` use Tesseract to locate and read on-screen text
- 🪟 **UIAutomation** — `click_control` / `set_text` / `list_controls` drive native Windows controls by accessibility name (the desktop analogue of CSS selectors)
- 🎯 **Animated cursor overlay** — glides to each action location, pulses, then fades — just like Sentinel Override's operator cursor
- 🔌 **20+ LLM providers** with native tool/function calling — OpenAI (ChatGPT), Anthropic (Claude), Google Gemini, xAI Grok, DeepSeek, OpenRouter, Groq, Mistral, Together, Fireworks, Cerebras, Perplexity, **Z.ai (GLM-5 / coding plan)**, **MiniMax**, **Moonshot (Kimi)**, **Qwen (Alibaba)**, **Cohere**, **NVIDIA NIM**, **HuggingFace**, **GitHub Models**, **DeepInfra**, Azure OpenAI, Ollama (local), LM Studio (local), and any OpenAI-compatible custom endpoint
- 🌐 **Three modes** — GUI, headless API, CLI (`--dry-run` flag to preview without acting)
- 🔒 **Safety stack** — approval gate per state-changing action, Esc-x3 panic stop, sensitive-field filter, tenant lockdown, dry-run
- 🔁 **Retry/backoff** on transient LLM errors with friendly error messages
- 📝 **Forensic logging** — structured per-step audit trail with JSON/CSV export
- 💾 **Checkpoint & Resume** — auto-saves state every 5 steps; resume after crash or close
- ⌨️ **Command palette (Ctrl+K)** — fuzzy-search commands, themes, settings
- 🎨 **14 themes** — Midnight, Dark, Matrix, Tron, Cyberpunk, Neon, Terminal, Blood, Ocean, Light, Sunset, Paper, Forest, Mono
- 🖥️ **Virtual Desktop isolation** — agent operates on its own Windows desktop, never interrupts the user
- 🥷 **Stealth input** — PostMessage / UIAInvoke for non-interrupting actions (no mouse/keyboard hijack)
- 📡 **WebSocket live feed** — every step broadcast to connected clients
- 🧠 **Neuralis Brain integration** *(v18.0)* — shared, fleet-wide memory: Sentinel writes what it learns and recalls what every other agent has learned, so it gets smarter with every task

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

# Dry-run (logs state-changing actions instead of executing them)
python main.py --dry-run -c "Open Notepad and type Hello World"
```

Or on Windows: double-click `install_and_run.bat`

## Safety hotkeys

Press **Esc three times within 1.5 seconds** to immediately stop the agent. This works globally and is independent of pyautogui's move-to-corner failsafe. Requires the optional `keyboard` package (installed by default).

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -q          # 5,244 tests
ruff check core/ gui/ api/ tests/   # zero lint errors
```

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
| `click_text` | OCR the screen, find visible text, click it (requires Tesseract) |
| `click_image` | Find and click a template image |
| `click_control` | Click a native Windows control by accessibility name (requires uiautomation) |
| `list_controls` | Enumerate accessible controls (buttons, edits, menus) in a window |
| `set_text` | Deterministically set the value of an editable control |
| `read_text` | OCR the entire screen and return its text |
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
│   ├── llm_client.py    # Multi-provider LLM client (20+ providers)
│   ├── provider_registry.py  # Provider catalog
│   ├── desktop.py       # Mouse, keyboard, screen control
│   ├── screenshot.py    # Screen capture + template matching + cache
│   ├── window_manager.py   # Window management
│   ├── process_manager.py  # Process management
│   ├── clipboard.py     # Clipboard read/write
│   ├── file_ops.py      # Safe file operations
│   ├── system_info.py   # System information
│   ├── control/         # Plan → Ground → Execute → Verify control loop
│   ├── perception/      # Multi-modal perception pipeline (accessibility + OCR + vision)
│   ├── platform/        # Cross-platform abstraction (Windows / Linux / macOS)
│   ├── swarm/           # Multi-agent orchestration (bus + registry + specialists)
│   ├── popup_handler.py # Automatic dialog detection and dismissal
│   ├── recovery.py      # Action retry and error recovery
│   ├── scheduler.py     # Cron-based task scheduling
│   ├── auth.py          # RBAC with bcrypt password hashing
│   ├── encryption.py    # Cross-platform encryption
│   └── ...              # 30+ more modules
├── api/
│   └── server.py        # FastAPI headless control server (35+ endpoints)
├── gui/
│   ├── app.py           # Main GUI window (cyberpunk HUD)
│   ├── themes.py        # 14 theme definitions
│   ├── overlay.py       # Action overlay + animated cursor
│   └── tabs/            # Settings, scripts, workflows, history tabs
├── scripts/it_support/  # 19 pre-built IT support script templates
├── tests/               # 5,244 tests, 99% coverage
└── requirements.txt
```

## Safety

- **Approval mode**: Every state-changing action requires user confirmation before execution (Approve / Reject dialog in the GUI)
- **Dry-run mode**: `--dry-run` logs every action it _would_ take without actually clicking or typing
- **Esc x3 failsafe**: Three rapid Esc presses stop the agent immediately, globally
- **pyautogui corner failsafe**: Move mouse to a screen corner to abort
- **Sensitive field protection**: Won't type strings that look like passwords or credentials
- **Tenant lockdown**: Restrict file access to tenant-scoped paths
- **Step budget**: Agent stops after N actions (configurable, default 100)
- **Bounded conversation**: Old screenshots are pruned from the LLM context so token cost stays predictable
- **LLM retry/backoff**: Transient 429/5xx errors retry with exponential backoff
- **API auth**: Set `SENTINEL_API_TOKEN` to require `Authorization: Bearer <token>` on every endpoint
- **Forensic log**: Every action logged with timestamp, params, and result

## Companion Projects

- **[Neuralis Brain](https://github.com/dirtysouthalpha)** — Shared, fleet-wide memory that every Sentinel-family agent reads from and writes to; the brain learns from all clients and gets better with every task
- **[Sentinel Override](https://github.com/dirtysouthalpha/sentinel-override)** — Browser automation agent (Chrome extension)
- **[Sentinel MCP](https://github.com/dirtysouthalpha/sentinel-mcp-server)** — Model Context Protocol server

## License

MIT
