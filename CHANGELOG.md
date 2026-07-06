# Changelog

## v25.0.0 (2026-07-05) — Enterprise & Polish
- New: Auto-update checker (`core/updater.py`) — checks GitHub releases for newer versions
- New: `/health` endpoint — system health for load balancers and monitoring (CPU, memory, engine status)
- New: `/update-check` endpoint — check if newer version available
- Version: unified to 25.0.0 across all modules
- Polish: all docstrings updated to v25.0.0

## v24.0.0 (2026-07-05) — Security & Reliability Hardening
- Fix: duplicate AgentEngine creation in `/goal` endpoint (reuse persistent engine, prevent memory leaks)
- New: rate limiting middleware (60 req/min per IP) on all API endpoints
- New: security headers on all responses (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy)
- New: input validation on goal endpoint (empty check, 10K char limit)
- New: DELETE method added to CORS allowed methods
- Fix: FastAPI app title unified from v2 to branded name
- Tests: updated _FakeEngine mock to support engine reuse pattern

## v23.0.0 (2026-07-05) — Architecture Consolidation
- Fix: unified all version strings to 23.0.0 (was split across 6.1.0/2.0.0/v3.0/22.0.2)
- Fix: rewrote requirements.txt with all 20+ real dependencies (was stale from v2.0 era)
- Fix: unified main.py routing — default GUI now uses v23 engine (`gui/app.py`)
- New: `--legacy-gui` flag for old v6.x GUI fallback (deprecated path)
- New: graceful fallback if new GUI dependencies are missing
- Updated all docstrings from v2.0/v3.0/v5.0 to unified version

## v22.0.2 (2026-07-03)
- CI: add mss to requirements.txt so screenshot tests pass on runners
- Tests: skip WindowsBackend test on non-Windows (pygetwindow Linux-incompatible)
- Tests: fix ctypes.windll leak from stealth_input fixture that broke Linux tests
- Fix: correct WindowsInfo -> WindowInfo typo in macos_backend
- Lint: ruff clean across core/gui/api/tests (70 auto-fixed + 1 manual)
- Format: ruff format applied to 66 files
- Version: bump 3.1.0 -> 22.0.2 to match latest tag series

## v5.0.0 (2026-06-23)
- Final release with comprehensive documentation
- 168 tests across all modules
- 13 command modules with full coverage
- 5 themes, plugin system, macro recording
- Voice TTS/STT integration

## v4.2.0 (2026-06-23)
- Edge case hardening (empty input, unicode, long strings)
- Integration tests for all 13 modules
- 168 tests

## v4.1.0 (2026-06-23)
- Voice commands module (TTS/STT)
- Engine detection of espeak, flite, say, SAPI
- 143 tests

## v4.0.0 (2026-06-23)
- Macro recording and playback

## v3.0.0 (2026-06-23)
- Web module (fetch/brief/open/search)

## v2.0.0
- Initial release
