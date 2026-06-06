# Sentinel Desktop — Ship History

Project milestones and their release dates.

## v7.0.0 — Perception: Grounding Revolution (2026-06-06)

**Shipped:**
- Phase 1: DPI & coordinate calibration (per-monitor scaling, HiDPI transform, calibration persistence)
- Phase 2: Hybrid grounding pipeline (a11y-first element map, ID-based targeting, vision fallback)
- Phase 3: Set-of-Marks screenshots (numbered bounding boxes, multi-source fusion, CV contour detection)
- Phase 4: Native computer-use adapters (Anthropic computer_20250124, OpenAI computer-use-preview, JSON fallback)
- Phase 5: Click verification & self-correction (post-action diff, tiered retry, enforced self-healing)
- Phase 6: Local grounding model (optional, feature-flagged, OmniParser/Florence-2/YOLO interface)
- 179 new tests across 6 test files
- Full suite: 5,337 tests passing, 0 failures

## v6.0.0 — Dependency Upgrades + Cleanup (2026-06-06)

**Shipped:**
- 11 dependency version bumps (fastapi, uvicorn, pydantic, websockets, httpx, bcrypt, pytest, ruff, mypy, pytest-asyncio, pytest-cov)
- 36 lint errors fixed (zero remaining)
- 12 test files fixed for Windows/Python 3.13 compatibility
- Version bumped to 6.0.0

## v3.1.0 — Production Foundation (2026-06-04)

**Shipped:**
- Critical GUI fixes (themes, approval mode)
- LLM retry/backoff and bounded conversation context
- 8 new LLM providers (MiniMax, Moonshot/Kimi, Qwen, Cohere, NVIDIA NIM, HuggingFace, GitHub Models, DeepInfra)
- OCR-backed `click_text` and `read_text` actions
- Windows UIAutomation integration
- Action overlay for visual feedback
- Pre-action callback hook for GUI integration
- Dry-run mode
- Esc-x3 failsafe
- Multi-monitor screenshot support
- Native tool/function calling
- WebSocket live feed
- API authentication
- Workflow builder CRUD API
- System dashboard with CPU/memory/disk/GPU metrics
- Popup handler (57 tests)
- Recovery engine expansion
- Test suite expansion (83 new tests)
- Docstrings and code quality improvements

## Future Milestones

*To be added...*
