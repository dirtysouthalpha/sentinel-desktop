# Sentinel Desktop — AI-Powered Windows Desktop Automation

**Vision-driven desktop automation agent. Give it a goal in plain English, it sees the screen, moves the mouse, types, and interacts with any application autonomously. Used daily by an IT Support Technician.**

---

## What This Is

Sentinel Desktop is a vision-based AI agent that automates Windows desktop interactions through natural language goals. It combines:

- **Computer vision** — Screenshot capture and OCR to understand screen state
- **LLM reasoning** — Multi-provider LLM integration for goal understanding and action planning
- **Desktop control** — Mouse, keyboard, clipboard, and Windows UIAutomation actions
- **Safety stack** — Approval gates, panic stops, and dry-run mode
- **Three modes** — Cyberpunk HUD GUI, headless API server, and CLI

**Primary user:** IT Support Technician who uses it daily for automation tasks.

---

## Core Value

**"Automate any Windows desktop task through natural language — safely, reliably, and with full visibility."**

Sentinel Desktop reduces repetitive IT support tasks to natural language descriptions. The technician says "Reset the user's Outlook profile" and the agent sees the screen, navigates Control Panel, and executes the steps.

---

## Current Milestone: v8.0.0 — Webhand (Browser & Web Command)

**Goal:** Embedded browser control via Playwright with DOM-aware web actions. Drive any web app / firewall UI by DOM, not pixels. Dual-mode: browser DOM for web apps, native vision for desktop.

**Target features:**
- Embedded controlled browser via Playwright (Chromium/Firefox/WebKit) with CDP
- DOM-aware web actions: web_open, web_click, web_type, web_read, web_extract, web_wait_for, web_screenshot, web_eval_js, web_download, web_upload, web_tabs
- Dual-mode unification: browser DOM mode for web apps, native vision mode for desktop
- Self-signed cert / appliance UX handling for IT admin web UIs
- Authenticated session vault (save/restore cookies per site, encrypted)
- Web recorder integration with core/recorder.py

---

## Validated Capabilities (What Exists)

### Core Engine
- Vision-driven agent loop with screenshot → LLM → action → verify cycle
- OCR text detection (Tesseract) for `click_text` and `read_text`
- Windows UIAutomation for control-level interaction
- Multi-monitor screenshot support (virtual desktop, primary, secondary)
- Screenshot downsampling and JPEG compression for token efficiency
- Image MIME type handling (PNG/JPEG)
- Conversation context bounding (image history limit)

### Actions
- Mouse: click, double_click, right_click, drag, mouse_move
- Keyboard: type, hotkey, paste
- Clipboard: get_clipboard, set_clipboard
- Files: list_files, read_file, write_file, delete_file
- Windows: close_window, kill_process, disk_usage
- UIAutomation: click_control, set_text, list_controls
- OCR: click_text, read_text
- Meta: wait, retry_last_action, note
- Workflow: execute_workflow (template-based automation)
- Screenshot: screenshot (multi-monitor support)

### LLM Integration
- 20+ providers with native tool/function calling:
  - OpenAI, Anthropic, Google Gemini, xAI Grok
  - DeepSeek, OpenRouter, Groq, Mistral, Together, Fireworks, Cerebras, Perplexity
  - Z.ai (GLM-5 family), MiniMax, Moonshot/Kimi, Qwen/Alibaba
  - Cohere, NVIDIA NIM, HuggingFace, GitHub Models, DeepInfra
  - Azure OpenAI, Ollama (local), LM Studio (local)
  - Custom OpenAI-compatible endpoints
- JSON action parser with balanced-brace scanning
- LLM retry/backoff with exponential backoff + jitter
- Human-readable error messages (Invalid API key, Model not found, etc.)

### Safety
- Approval gate per state-changing action
- Esc-x3 panic stop (three rapid Esc presses)
- Sensitive-field filter (redacts passwords, API keys)
- Dry-run mode for preview without execution
- Tenant lockdown (configurable working directory)

### Reliability
- Checkpoint & Resume (auto-saves every 5 steps)
- Forensic logging with JSON/CSV export
- Bounded conversation context (image_history limit)
- Robust error handling with specific exception types

### GUI (Cyberpunk HUD)
- 14 themes (Midnight, Dark, Matrix, Tron, Cyberpunk, Neon, Terminal, Blood, Ocean, Light, Sunset, Paper, Forest, Mono)
- Animated cursor overlay (glides, pulses, fades like Sentinel Override)
- Action overlay (orange ring + label at target coordinates)
- Approval dialog for state-changing actions
- Command palette (Ctrl+K) for fuzzy search
- System tray integration
- Thread-safe widget updates (marshaled to Tk main thread)
- Real-time agent step display

### API Server (Headless)
- 35+ REST endpoints (POST /command, GET /config, GET /health, etc.)
- WebSocket live feed (/ws) for real-time step broadcasting
- API authentication (SENTINEL_API_TOKEN)
- CORS configuration (localhost-only by default)
- Workflow builder CRUD (templates, steps, execution)
- System dashboard (CPU, memory, disk, GPU metrics)

### Testing
- 138 test files, 4,973 tests passing (99% coverage)
- Platform-specific test skips (Win32 ctypes on Linux)
- CI coverage reporting (pytest with --cov)
- Smoke tests across 7 modules

### Documentation
- Google-style docstrings on all public functions
- Module headers explaining purpose and usage
- CLAUDE.md with project instructions and priorities
- README with features, quick start, and examples

---

## Active Requirements

- [ ] WEB-01: Embedded controlled browser via Playwright with CDP support
- [ ] WEB-02: web_open action — navigate to URL in managed browser
- [ ] WEB-03: web_click action — click by CSS selector, text content, or ARIA role
- [ ] WEB-04: web_type action — type text into form fields by selector/label
- [ ] WEB-05: web_read action — extract text content from page or element
- [ ] WEB-06: web_extract action — extract structured data (tables, lists, forms)
- [ ] WEB-07: web_wait_for action — wait for element, navigation, or network idle
- [ ] WEB-08: web_screenshot action — capture browser viewport as image
- [ ] WEB-09: web_eval_js action — execute JavaScript in browser context
- [ ] WEB-10: web_download action — download files from browser
- [ ] WEB-11: web_upload action — upload files to web forms
- [ ] WEB-12: web_tabs action — list, switch, create, close browser tabs
- [ ] DUAL-01: Engine auto-detects web vs native context and routes to browser or vision mode
- [ ] DUAL-02: Mid-task handoff between browser and native mode
- [ ] CERT-01: Auto-accept self-signed cert warnings for whitelisted appliance hosts
- [ ] CERT-02: Login form detection for common IT admin web UIs
- [ ] SESS-01: Session vault saves cookies + localStorage per site, encrypted
- [ ] SESS-02: Session vault restores cookies on return visits
- [ ] REC-01: Web recorder captures browser interactions into replayable scripts

---

## Out of Scope

- **Mobile platform support** — Windows-only desktop automation
- **Web browser automation** — Focus on native desktop applications
- **Custom action plugins** — Plugin system exists but not a priority
- **Voice input** — Text-based natural language only
- **Learning from user behavior** — No ML adaptation or personalization

---

## Key Technical Decisions

### LLM Provider Architecture
- Multi-provider support via adapter pattern (one interface, many providers)
- Native tool/function calling preferred over JSON-in-text
- Fallback to JSON parsing for providers without tool support
- Retry/backoff for transient errors (408/425/429/5xx)

### Screenshot Strategy
- Multi-monitor support via mss library (virtual desktop, primary, secondary)
- JPEG compression for token efficiency
- PNG default for MIME type compatibility
- Conversation context bounding (image_history limit)

### Safety Model
- Approval gate per state-changing action
- Esc-x3 panic stop (optional keyboard package)
- Dry-run mode for preview
- Sensitive-field filter for redaction

### Testing Strategy
- 99% coverage target (well above ≥80% minimum)
- Platform-specific skips for Win32 ctypes on Linux
- CI coverage reporting with term-missing and XML

---

## Context

### State
- **Version:** v6.0.0 (production-ready)
- **Tests:** 4,907 passing, 12 skipped, 337 in ctypes-mock files (pre-existing)
- **Coverage:** 99%
- **Lint:** Zero errors (ruff check clean across core/gui/api/tests)
- **Platforms:** Windows primary, Linux development/testing

### Project Structure
- **core/** — 43 modules (agent loop, LLM client, screenshot, OCR, UIAutomation, actions, scheduler, workflows)
- **gui/** — 13 modules (app, cursor overlay, themes, tabs, system tray)
- **api/** — FastAPI server (35+ endpoints, workflow builder, system dashboard)
- **plugins/** — Plugin system (not prioritized)
- **scripts/** — 21 IT support scripts (JSON templates)
- **tests/** — pytest suite (138 test files)

### Tech Stack
- Python 3.10+ with type hints
- Google-style docstrings
- 4-space indentation
- ruff for linting
- pytest for testing
- pyautogui for mouse/keyboard
- pytesseract for OCR
- mss for screenshots
- FastAPI for API server
- tkinter for GUI

---

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---

*Last updated: 2026-06-06 — Milestone v8.0.0 Webhand initialized*
