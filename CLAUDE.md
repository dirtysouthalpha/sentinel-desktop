# Sentinel Desktop — AI-Powered Windows Desktop Automation

Vision-driven desktop automation agent. Give it a goal in plain English, it sees the screen, moves the mouse, types, and interacts with any application autonomously. Used daily by an IT Support Technician.

## What To Do (Priority Order)
1. Run `python -m pytest tests/ -q` — fix ALL failing tests first.
2. Run `ruff check core/ gui/ api/` — fix ALL lint errors.
3. Finish in-progress features:
   - `api/server.py` — workflow builder API endpoints need handler bodies completed (_handle_workflow_add_step, _handle_workflow_remove_step, etc.)
   - `core/dashboard.py` — system dashboard with CPU/memory/disk/GPU metrics. Verify all endpoints work.
   - `core/workflow_builder.py` — workflow CRUD, templates, step management. Verify roundtrip.
   - `scripts/it_support/` — IT support script templates (account unlock, event log scan, network diagnostics, password reset). Verify they load and execute.
4. Improve test coverage — add tests for untested modules in core/ and gui/.
5. Fix any bugs, improve error handling, reduce complexity.
6. After each logical unit of work: commit with a descriptive message and push.

## Commands
- Test: `python -m pytest tests/ -q`
- Lint: `ruff check core/ gui/ api/`
- Run GUI: `python main.py`
- Run API: `python main.py --api --port 8091`

## Architecture
- **core/** — Core engine (43 modules): agent loop, LLM client, screenshot, OCR, UIAutomation, actions, scheduler, workflows
- **gui/** — Cyberpunk HUD GUI with tkinter (13 modules): app, cursor overlay, themes, tabs, system tray
- **api/** — FastAPI headless server (35+ endpoints)
- **plugins/** — Plugin system
- **scripts/** — Pre-built IT support scripts (JSON templates)
- **tests/** — pytest suite (~40+ test files)
- Multi-provider LLM support (20+ providers including OpenAI, Anthropic, Google, xAI, Z.ai GLM-5)

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
