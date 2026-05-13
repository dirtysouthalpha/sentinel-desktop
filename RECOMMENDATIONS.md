# Sentinel Desktop — Recommendations

This document is a prioritized punch list of concrete improvements based on
an audit of the repository on 2026-05-13. Each item carries a file path (and
line number where useful) so it can be picked up directly.

Items implemented on the same branch that introduced this document are
marked **[done in this PR]**. Everything else is a follow-up.

---

## Top 10 highest-impact

1. **No packaging metadata — repo can't be `pip install`'d.** No
   `pyproject.toml`, `setup.py`, or `setup.cfg`; no console entry point.
   **[done in this PR]** — added `pyproject.toml` (PEP 621),
   `core.__version__`, optional extras (`ocr`, `windows`, `tray`, `dev`).

2. **No CI / pre-commit / lint.** No `.github/workflows`, no
   `.pre-commit-config.yaml`, no ruff or black config — every contributor
   has a different style and nothing gates regressions. **[done in this
   PR]** — added `.github/workflows/ci.yml` (ruff + mypy + pytest +
   pip-audit) and `.pre-commit-config.yaml`.

3. **Unpinned dependencies.** `requirements.txt:1-39` uses `>=` on every
   package — a minor bump in `customtkinter`, `opencv-python`, or
   `pyautogui` can break the build silently. **[done in this PR]** —
   rewritten with `~=` compatible-release pins.

4. **Path traversal in `core/file_ops.py`.** `read_file`, `write_file`,
   `list_directory` accept any absolute path with no sandboxing. The
   `tenant_lockdown` flag declared in `config.py:29` is unenforced. README
   advertises "Tenant lockdown: Restrict file access to tenant-scoped
   paths." **[done in this PR]** — sandbox resolution under
   `~/SentinelDesktop` (or `SENTINEL_SANDBOX_ROOT`) when lockdown is on.

5. **PowerShell command injection in `core/powershell.py`.**
   `restart_service(name)`, `get_service_status(name)`,
   `test_connection(host)` all build commands with f-string interpolation
   directly into single-quoted PowerShell strings — a `name` containing
   `'; Stop-Computer; '` escapes the quoting. **[done in this PR]** — added
   `_ps_escape_single_quoted` and an `allow_raw` flag for the raw
   `run_command` / `run_inline` surface.

6. **Shell-metachar injection in `core/launcher.py`.** Unknown app names
   are passed verbatim to `cmd /c start "" <name>` (`launcher.py:111-117`).
   `name="foo & calc"` resolves and executes `calc`. **[done in this PR]**
   — `_is_safe_launch_token` rejects shell metacharacters on the
   unknown-name fallback path; curated `APP_ALIASES` stay trusted.

7. **Broken installer build.** `installer/build.py:33-48` lists
   `core.forensic` (actual: `core.forensic_log`), `core.mfa_detector`
   (actual: `core.mfa_detection`), `gui.tabs.settings_tab` is missing.
   PyInstaller will fail to find these as hidden imports. **[done in this
   PR]** — module names corrected, gui.tabs.* gated on existence, file
   write set to UTF-8, AppId given a stable GUID.

8. **Version drift.** `main.py:3,37`, `config.py:2`, `requirements.txt:1`,
   `README.md:3` say "v2"; `core/powershell.py:2`, `installer/build.py:1,22`,
   `core/auth.py:2` say "v3.0". **[done in this PR]** — `core.__version__`
   is the single source of truth; READMEs and docstrings updated.

9. **`mypy.ini` targets EOL Python 3.8.** Python 3.8 reached EOL in
   Oct 2024. **[done in this PR]** — bumped to 3.10 to match
   `pyproject.toml`.

10. **244 bare `except Exception` sites swallow errors.** Audit found
    ~244 occurrences across the codebase. Hot files include
    `core/file_ops.py`, `core/launcher.py`, `core/powershell.py`,
    `config.py`. **[partially done in this PR]** for `file_ops.py` and
    `launcher.py` only. Remaining cleanup is a follow-up.

---

## Code quality & structure

- `core/engine.py` is large and `AgentEngine.run()` should be split into
  `_take_screenshot`, `_call_llm`, `_dispatch_and_wait` for testability.
- `core/action_executor.py` maintains a manual dispatch dict; adding new
  actions requires touching `tool_schemas.py`, the dispatch table, and the
  docstring. Replace with a `@action("click")` decorator pattern that
  populates a registry on import.
- No `__all__` exports in `core/__init__.py`, `api/__init__.py`, `gui/__init__.py`
  — public API is ambiguous.
- No action-schema validation on parsed LLM output (`core/engine.py`
  `_parse_action`). Use `pydantic.BaseModel` per action type so a malformed
  action surfaces a clear error rather than `{"action": "unknown"}`.

## Security

- **Path traversal** in `core/file_ops.py` — **[done]**.
- **PowerShell injection** in `core/powershell.py` — **[done for helpers]**;
  `run_command` / `run_inline` remain caller-trusted with `allow_raw` flag.
- **Launcher injection** in `core/launcher.py` — **[done]**.
- **Subprocess in `core/powershell.py` admin elevation** (lines 137-147)
  builds a string `wrapped` containing the user command embedded in
  `-ArgumentList` quoting. Quoting collisions remain possible even after
  the helper escape — keep `run_as_admin=True` behind an approval gate.
- **No TLS verification asserted** in `core/llm_client.py` — explicitly
  pass `verify=True` to `requests.Session` / `httpx.Client` so an
  environment `REQUESTS_CA_BUNDLE` override can't silently disable.
- **`DEFAULT_ADMIN_PASSWORD = "sentinel"` in `core/auth.py:30`** — the
  bootstrap admin account ships with a known password. On first start
  the user must rotate; document this and consider failing the API server
  startup when the default password is still in use.
- **SHA-256 password hashing in `core/auth.py:_hash_password`** is too
  fast for password verification — migrate to `bcrypt` / `argon2-cffi`.

## Testing

- `pytest -q` passes locally with the existing 36 smoke tests but **no CI
  runs them on PRs** — fixed by `.github/workflows/ci.yml` **[done]**.
- Coverage of the agent loop (`core/engine.py`) is shallow; no integration
  test of screenshot → LLM → action.
- No tests for `core/auth.py` permission tables — RBAC bugs would ship.
- No tests for the FastAPI server (`api/server.py`) — at minimum add a
  TestClient-based test that hits `/status`, `/config`, `/goal` happy paths.
- New security tests added in this PR:
  - `tests/test_file_ops.py` — path-traversal cases.
  - `tests/test_launcher.py` — shell-metachar rejection.
  - `tests/test_powershell_safety.py` — PS string escaping.

## Error handling & robustness

- Bare `except Exception` in `config.py:128`, `config.py:141`, `file_ops.py`,
  `launcher.py`, `powershell.py:102,201` — narrow to `(OSError,
  json.JSONDecodeError)` etc. Re-raise programming errors.
- No retry on transient file I/O — `Config.load` (`config.py:120`) should
  retry a couple of times before falling back to defaults (a transient AV
  lock on Windows is common).
- LLM error mapping in `core/llm_client.py` is per-provider — extract a
  shared exception hierarchy so the GUI can show one consistent message.
- Screenshot capture races with window focus: `core/screenshot.py` captures
  before the focused window has fully repainted on slow machines. A small
  `time.sleep(0.05)` plus a focus check would help.

## Dependencies

- All `>=` pins replaced with `~=` **[done]**.
- `pyautogui>=0.9.54` — last released 2023; consider `pynput` as backup
  for the keyboard/mouse path.
- `keyboard>=0.13.5` — last released 2022, has no maintainer; the Esc-x3
  failsafe could be implemented with `pynput` instead.
- `pytesseract` requires the Tesseract binary; document this in README.

## Documentation

- README badge says `Python 3.8+` — update to `3.10+` to match the new
  `pyproject.toml`. **[done]**
- README's "20+ LLM providers" claim — actual count in
  `core/provider_registry.py` is 16 first-class + several placeholders.
- README API table lists endpoints that the audit suggests don't exist
  (`/recorder/start`, `/workflows/run`) — verify and prune or implement.
- `CHANGELOG.md` is still `## Unreleased` despite the code carrying v3
  markers — add a `## 3.0.0` heading.
- `ROADMAP-v3.md` reads as if features are shipped — clarify per item
  whether shipped vs. planned.

## Performance

- Screenshots always encoded as PNG. Adding JPEG (with `screenshot_quality`)
  for the LLM context could cut tokens 3-4x.
- `core/engine.py` keeps a sliding window of `image_history=3` screenshots
  but re-encodes each one on every loop iteration — cache base64 in
  the conversation buffer.
- No memoization between identical goals — a "replay last goal" feature
  could short-circuit screenshot + LLM round trips for known stable flows.

## Packaging & distribution

- `pyproject.toml` added **[done]** with PEP 621 metadata and console
  entry point `sentinel-desktop = "main:main"`.
- `installer/build.py` HIDDEN_IMPORTS fixed **[done]**.
- No GitHub Release workflow that builds the EXE on a `tag`. Add a
  `release.yml` that runs `python installer/build.py --all` on Windows
  and uploads the artifact.
- No SBOM / dependency review — `pip-audit` is wired into CI as
  informational; consider making it blocking after triage.

## DevEx

- `.pre-commit-config.yaml` added **[done]**.
- `.github/workflows/ci.yml` added **[done]**.
- No `Makefile` / `tasks.py` — common one-liners like `make test`,
  `make lint`, `make fmt` would help. Optional.
- `mypy.ini` `allow_untyped_defs = True` defeats type-checking — keep
  permissive for now, tighten module-by-module under `[mypy-core.engine]`
  etc.

---

## How this PR maps to the list

| Area                       | Status                              |
|---------------------------|--------------------------------------|
| Packaging                 | done — pyproject.toml + entry point  |
| CI / lint / pre-commit    | done                                 |
| Dependency pinning        | done — `~=` compatible-release       |
| Path traversal            | done                                 |
| PowerShell injection      | done                                 |
| Launcher injection        | done                                 |
| Installer module names    | done                                 |
| Version drift             | done                                 |
| mypy py-version bump      | done                                 |
| 244 bare-except cleanup   | partial — hot files only             |
| Engine refactor           | follow-up                            |
| RBAC password hashing     | follow-up                            |
| GUI thread-safety audit   | follow-up                            |
| Strict mypy module rollout| follow-up                            |
| README API accuracy       | follow-up                            |
| Release workflow / SBOM   | follow-up                            |
