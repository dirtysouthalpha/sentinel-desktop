# Sentinel Desktop v2.0

> AI-powered Windows desktop automation assistant with Neuralis Brain integration.

[![CI](https://github.com/dirtysouthalpha/sentinel-desktop/actions/workflows/ci.yml/badge.svg)](https://github.com/dirtysouthalpha/sentinel-desktop/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Features

- **System Diagnostics**: CPU, memory, disk, processes, battery, temperature, uptime
- **Mouse & Keyboard Automation**: Click, type, press keys, scroll, drag
- **Network Tools**: Ping, IP config, full diagnostics, speedtest
- **Process Management**: Open/close applications
- **File Operations**: List, search, read files
- **Neuralis Brain AI**: Claude-like reasoning via Neuralis Brain REST API
- **Professional UI**: Dark-themed chat interface with real-time system monitoring

## Installation

### Quick Install (Windows)

Download and run `install_and_run.bat` from the latest release.

### Manual Install

```bash
git clone https://github.com/dirtysouthalpha/sentinel-desktop.git
cd sentinel-desktop
pip install -r requirements.txt
python main.py
```

### CLI Mode

```bash
python main.py --cli
```

## Usage

Type natural language commands in the chat interface:

### System
| Command | Description |
|---------|-------------|
| `cpu` | Show CPU usage |
| `memory` | Show RAM usage |
| `disk` | Show disk usage |
| `processes` | List top processes |
| `battery` | Show battery status |
| `uptime` | Show system uptime |

### Automation
| Command | Description |
|---------|-------------|
| `click 500,300` | Click at coordinates |
| `click right 500,300` | Right-click |
| `type hello world` | Type text |
| `press ctrl+c` | Press key combo |
| `move 100,200` | Move mouse |
| `scroll 3` | Scroll up/down |
| `drag 100,200 to 300,400` | Drag mouse |
| `screenshot` | Take screenshot |

### Network
| Command | Description |
|---------|-------------|
| `ping google.com` | Ping a host |
| `ipconfig` | Show IP config |
| `network diagnostics` | Full network check |
| `speedtest` | Run speed test |

### Process
| Command | Description |
|---------|-------------|
| `open chrome` | Launch app |
| `close notepad` | Kill process |

### AI (Neuralis Brain)
| Command | Description |
|---------|-------------|
| `brain status` | Check brain health |
| `recall <topic>` | Recall knowledge |
| `think <topic> <content>` | Store knowledge |

## Architecture

```'
Sentinel Desktop v2.0
├── main.py              # Entry point (GUI + CLI modes)
├── src/
│   ├── config.py        # Central configuration
│   ├── cli.py           # CLI mode
│   ├── core/
│   │   ├── engine.py    # Command router & NLP parser
│   │   └── brain.py     # Neuralis Brain API client
│   ├── commands/
│   │   ├── system.py    # System diagnostics
│   │   ├── automation.py # Mouse & keyboard
│   │   ├── network.py   # Network tools
│   │   ├── process.py   # Process management
│   │   └── files.py     # File operations
│   ├── ui/
│   │   └── app.py       # CustomTkinter GUI
│   └── utils/
│       ├── logger.py    # Logging
│       └── helpers.py   # Helpers
├── tests/               # Pytest test suite
├── .github/workflows/   # CI/CD pipelines
└── setup.py             # Package config
```

## Configuration

Config stored at `~/.sentinel-desktop/config.json`:

```json
{
  "brain_url": "http://100.70.240.55:8001",
  "brain_enabled": true,
  "appearance": "dark",
  "screenshot_format": "png",
  "mouse_speed": 0.3
}
```

## Requirements

- Python 3.8+
- Windows OS (optimized for Windows, works on Linux)
- Dependencies: customtkinter, pyautogui, psutil, requests

## License

MIT License - see [LICENSE](LICENSE)
