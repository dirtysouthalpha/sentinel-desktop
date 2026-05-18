# Sentinel Desktop — AI-Powered Windows Desktop Automation

Vision-driven desktop automation agent. Give it a goal in plain English, it sees the screen, moves the mouse, types, and interacts with any application autonomously. Used daily by an IT Support Technician.

## What To Do (Priority Order)
1. Run `python -m pytest tests/ -q` — fix ALL failing tests first.
2. Run `ruff check core/ gui/ api/` — fix ALL lint errors.
3. Improve test coverage — add tests for any remaining untested modules in core/ and gui/. Target: every module should have ≥80% branch coverage.
4. Finish remaining in-progress features:
   - `api/server.py` — workflow builder API endpoints need handler bodies completed (_handle_workflow_add_step, _handle_workflow_remove_step, etc.)
   - `scripts/it_support/` — verify all IT support script templates load and execute correctly
5. Edge case hardening:
   - Test recovery engine with various failure scenarios
   - Test scheduler overlap protection edge cases
   - Test LLM client with malformed responses and timeouts
   - Test popup handler with nested dialogs
6. Performance optimizations:
   - Profile OCR pipeline and reduce processing time
   - Optimize screenshot capture frequency
   - Add caching for repeated UI element lookups
7. Documentation:
   - Add docstrings to any undocumented public functions
   - Ensure every module has a header comment explaining its purpose
8. Code quality:
   - Refactor any functions over 50 lines into smaller units
   - Consolidate duplicate utility functions across modules
   - Narrow remaining bare `except` clauses to specific exception types
   - Ensure all async operations have proper timeout handling
9. After each logical unit of work: commit with a descriptive message and push.

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
- **tests/** — pytest suite with 138 test files
- Multi-provider LLM support (20+ providers including OpenAI, Anthropic, Google, xAI, Z.ai GLM-5)

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
