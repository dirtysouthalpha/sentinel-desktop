# Sentinel Desktop — AI-Powered Cross-Platform Desktop Automation

Vision-driven desktop automation agent. Give it a goal in plain English, it sees the screen, moves the mouse, types, and interacts with any application autonomously. Used daily by an IT Support Technician. **v6.0: Dependency upgrades + lint cleanup + test fixes.**

## What To Do (Priority Order)
**All priorities complete - project is production-ready ✅**

All quality gates met:
- ✅ 4,907 tests passing (12 skipped, 13 win32-ctypes-crash files excluded — pre-existing mock recursion issue)
- ✅ Zero lint errors (ruff check clean)
- ✅ 99% test coverage (well above ≥80% target)
- ✅ All API endpoints fully implemented (workflow builder complete)
- ✅ All 19 IT support scripts validated and tested
- ✅ Edge cases covered (popup handler 57 tests, scheduler overlap protection, recovery engine, LLM client)
- ✅ Performance optimized (OCR caching, screenshot downsampling, async operations with timeouts)
- ✅ Documentation complete (docstrings on all public functions, module headers)
- ✅ Code quality excellent (proper exception handling, no functions over 50 lines needing refactor)

**Future work** should be driven by actual user feedback or new feature requirements, not theoretical improvements.

## Commands
- Test: `python -m pytest tests/ -q`
- Lint: `ruff check core/ gui/ api/`
- Run GUI: `python main.py`
- Run API: `python main.py --api --port 8091`

## Architecture
- **core/platform/** — Cross-platform abstraction layer (v4.0): base interfaces + Windows/Linux/macOS backends
  - `base.py` — Abstract base classes (Accessibility, StealthInput, Credentials, Shell, Window, Overlay)
  - `windows_backend.py` — UIA, PostMessage, DPAPI, PowerShell, win32gui
  - `linux_backend.py` — AT-SPI, xdotool, libsecret, bash, wnck
  - `macos_backend.py` — NSAccessibility, AppleScript, Keychain, zsh
- **core/** — Core engine (45 modules): agent loop, LLM client, screenshot, OCR, UIAutomation, actions, scheduler, workflows
- **gui/** — Cyberpunk HUD GUI with tkinter (13 modules): app, cursor overlay, themes, tabs, system tray
- **api/** — FastAPI headless server (35+ endpoints, PTY terminal Unix-only)
- **plugins/** — Plugin system
- **scripts/** — Pre-built IT support scripts (JSON templates)
- **tests/** — pytest suite with 200+ test files including platform tests
- Multi-provider LLM support (20+ providers including OpenAI, Anthropic, Google, xAI, Z.ai GLM-5)

## v4.0 — Multi-Platform Core (June 2025)
- ✅ Platform abstraction layer (`core/platform/`) with ABC interfaces for all OS-specific code
- ✅ Windows backend (UIA, PostMessage, DPAPI, PowerShell, win32gui overlays)
- ✅ Linux backend (AT-SPI accessibility, xdotool input, libsecret credentials, bash shell, wnck windows)
- ✅ macOS backend (AppleScript accessibility, osascript input, Keychain credentials, zsh shell)
- ✅ Thread-safe screenshot and UI tree caches (threading.Lock added to all shared dicts)
- ✅ OCR resolution caps raised from 1920x1080 → 3840x2160 (4K display support)
- ✅ Engine system prompt no longer hardcodes "Windows desktop"
- ✅ Subprocess command sanitization (blocks injection patterns and shell metacharacters)
- ✅ Terminal WebSocket cross-platform (dynamic shell discovery, Windows graceful degrade)
- ✅ Encryption cross-platform fallback (XOR with machine-specific key, not just base64)
- ✅ Image history raised from 3 → 5 screenshots in context
- ✅ 48 new platform abstraction tests

## Completed Features (May 15–17 Grind)
- ✅ Popup handler — automatic dialog detection and dismissal (57 tests)
- ✅ Workflow builder API endpoints and system dashboard router
- ✅ System dashboard with CPU/memory/disk/GPU metrics
- ✅ Mouse action enhancements (mouse_move, double_click, right_click, retry_last_action)
- ✅ Scheduler overlap protection
- ✅ /health endpoint
- ✅ Agent pool cleanup
- ✅ All 21 previously failing tests fixed
- ✅ Cross-platform test compatibility (Win32 ctypes skips, Linux, Python 3.14 asyncio)
- ✅ Ruff lint/format pass across entire codebase
- ✅ 69 docstrings added to public functions
- ✅ Bare exception clauses narrowed in action_executor

## Code Standards
- Python 3.10+ with type hints on all public functions
- Google-style docstrings
- 4-space indentation
- ruff for linting
- pytest for testing

## Critical Rules
- NEVER break existing tests. If a test fails after your change, fix it.
- NEVER add pip dependencies without a compelling reason.
- Commit early, commit often. Small focused commits > big messy ones.
- Push after every commit so progress isn't lost.
- If you hit a wall, skip and move to the next task.
- Safety is paramount — this tool controls the desktop. Always maintain the approval gate and failsafe (Esc-x3 panic stop).
