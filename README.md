# Sentinel Desktop v5.0.0

AI-powered desktop automation assistant with natural language commands, system monitoring, and Neuralis Brain integration.

## Features

### 13 Command Modules

| Module | Commands | Description |
|--------|----------|-------------|
| **System** | cpu, memory, disk, processes, battery, temperature, uptime, sysinfo | Real-time system monitoring |
| **Automation** | click, type, press, move, scroll, drag, screenshot | Mouse & keyboard control |
| **Network** | ping, ipconfig, diagnostics, speedtest | Network troubleshooting |
| **Process** | open, kill, close | Application management |
| **Files** | list, find, read | File operations |
| **Clipboard** | copy, paste, read | Clipboard management |
| **Windows** | list windows | Window enumeration |
| **Media** | volume up/down/mute, play/pause, next/prev track | Media playback control |
| **Power** | shutdown, restart, sleep, lock, cancel | Power management |
| **Notify** | notify, alert, remind | System notifications |
| **Scheduler** | timer, list timers, cancel timer | Countdown timers |
| **Voice** | speak, listen, status | Text-to-speech & speech-to-text |
| **Macros** | record, save, load, list, delete | Automation recording |
| **Plugins** | list, load | Extensible plugin system |

### Additional Features

- **Neuralis Brain AI** integration for natural language queries
- **5 Built-in Themes** (dark, midnight, forest, sunset, ocean)
- **Plugin System** for custom command extensions
- **Macro Recording** for automating repetitive tasks
- **Voice Commands** with TTS/STT support
- **System Tray** integration
- **Keyboard Shortcuts**: Ctrl+L (clear), Ctrl+Enter (send)
- **Command History** navigation (Up/Down arrows)

## Installation

### From Source

```bash
git clone https://github.com/dirtysouthalpha/sentinel-desktop.git
cd sentinel-desktop
pip install -r requirements.txt
python main.py
```

### From Release

Download the latest Windows EXE from [Releases](https://github.com/dirtysouthalpha/sentinel-desktop/releases).

### CLI Mode

```bash
python -m src.cli "cpu"
python -m src.cli "screenshot"
python -m src.cli "ping google.com"
```

## Architecture

```
sentinel-desktop/
├── src/
│   ├── core/
│   │   ├── engine.py      # Command router & dispatcher
│   │   ├── brain.py       # Neuralis Brain REST client
│   │   └── plugins.py     # Plugin manager
│   ├── commands/
│   │   ├── system.py      # System monitoring
│   │   ├── automation.py   # Mouse/keyboard automation
│   │   ├── network.py      # Network tools
│   │   ├── process.py      # Process management
│   │   ├── files.py        # File operations
│   │   ├── clipboard.py    # Clipboard tools
│   │   ├── windows.py      # Window management
│   │   ├── media.py        # Media controls
│   │   ├── power.py        # Power management
│   │   ├── notify.py       # Notifications
│   │   ├── scheduler.py    # Timers & scheduling
│   │   ├── voice.py        # Voice TTS/STT
│   │   └── macros.py       # Macro recording
│   ├── utils/
│   │   └── themes.py       # Theme system (5 themes)
│   ├── ui/
│   │   └── app.py          # CustomTkinter GUI
│   ├── agent/
│   │   └── agent.py        # AI agent mode
│   ├── config.py           # Configuration
│   └── cli.py              # CLI interface
├── tests/                  # 168 tests
├── plugins/                # Plugin directory
├── macros/                 # Saved macros
├── docs/                   # Documentation
└── main.py                 # Entry point
```

## Testing

```bash
python -m pytest tests/ -v
```

168 tests covering all modules, edge cases, and integration paths.

## CI/CD

- **CI**: flake8 lint + pytest on Ubuntu & Windows (Python 3.9-3.12)
- **Build**: Windows EXE via PyInstaller
- **Release**: Auto-published tar.gz + zip + EXE on tag push

## Plugin Development

Create a file in `plugins/plugin_myplugin.py`:

```python
def run():
    print("Hello from my plugin!")
```

Then load it: `load plugin plugin_myplugin`

## Requirements

- Python 3.9+
- psutil, pyautogui, customtkinter, Pillow

## License

MIT License

## Author

Brandon (dirtysouthalpha)
