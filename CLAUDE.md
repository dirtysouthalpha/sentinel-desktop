# Sentinel Desktop — Autonomous Grinding Instructions

## Project
AI-powered Windows desktop automation agent. Python, tkinter GUI, OpenAI-compatible LLM provider support, OCR, UIAutomation, 37+ action types.

## What To Do (Priority Order)
1. **Run tests first** — `python -m pytest tests/ -q` — see what's failing and fix those first
2. **Fix all 15 failing tests** — see test_action_parsing.py, test_autonomous_and_offset.py, test_config.py, test_engine_unconfigured.py, test_message_pruning.py
3. **Run ruff** — `ruff check . && ruff format .` — fix any lint/format issues
4. **Look for gaps** — read the ROADMAP-v3.md, find features that are partially implemented, complete them
5. **Improve test coverage** — write tests for uncovered modules (especially new ones like recorder.py, script_engine.py, workflow.py, scheduler.py)
6. **Check for TODO/FIXME comments** — fix any you find
7. **Commit and push after each unit of work** — `git add -A && git commit -m "description" && git push origin main`
8. **Repeat** — keep going until there's genuinely nothing left to improve

## Code Standards
- Python 3.10+, type hints on all public functions
- Ruff for linting and formatting
- pytest for testing
- All modules in core/ for logic, gui/ for UI, api/ for web server
- Provider-agnostic LLM client (supports 25+ providers)

## Commands
- `python -m pytest tests/ -q` — run all tests
- `ruff check .` — lint
- `ruff format .` — format
- `git push origin main` — push to GitHub

## Critical Rules
- NEVER break existing passing tests
- NEVER add __pycache__, .pyc, or venv files to git
- ALWAYS commit and push after completing a unit of work
- If you run out of max-turns, the next session will pick up where you left off — just continue improving
