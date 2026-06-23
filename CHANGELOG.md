# Changelog

## [v2.3.0] - 2026-06-23

### Added
- Settings panel UI (Brain URL, mouse speed, screenshot format)
- 7 new engine routing tests (clipboard, windows, help, ?)
- Settings gear button in header

### Changed
- Version bumped to 2.3.0

## [v2.2.0] - 2026-06-23

### Added
- Clipboard commands (copy text, read clipboard)
- Window management (list open windows)
- 11 new tests (clipboard + windows)
- Help system updated with all command categories

## [v2.1.0] - 2026-06-23

### Added
- Help command with full command reference
- Keyboard shortcuts (Ctrl+L clear, Ctrl+Enter send)
- Command history navigation (Up/Down arrows)

## [v2.0.0] - 2026-06-23

### Complete Rewrite
- Modular architecture: src/ with core/, commands/, ui/, utils/
- Neuralis Brain AI integration (recall, think, search)
- System diagnostics: CPU, memory, disk, processes, battery, temp, uptime
- Mouse & keyboard automation: click, type, press, move, scroll, drag, screenshot
- Network tools: ping, ipconfig, diagnostics, speedtest
- Process management: open/close applications
- File operations: list, search, read
- Professional dark-themed CustomTkinter UI with system monitor
- CLI mode and GUI mode
- 43 tests across 8 test files
- Full CI/CD pipeline (lint + test matrix + Windows EXE build + release)
- Cross-platform: Ubuntu + Windows, Python 3.9-3.12
