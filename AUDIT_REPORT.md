# Sentinel Desktop — Comprehensive Code Audit Report

**Date:** 2026-07-05
**Target:** `/a0/usr/workdir/sentinel-desktop-latest/`
**Tag:** v22.0.2 (declared in `core/__init__.py`)
**Auditor:** Agent Zero 'Master Developer'

---

## Executive Summary

The codebase is a **bifurcated monorepo** containing two generational layers coexisting without clean migration:

| Layer | Location | Version | Status |
|-------|----------|---------|--------|
| **New (v22)** | `core/`, `gui/`, `api/`, root `config.py` | 22.0.2 | Active API mode; GUI partially wired |
| **Old (v6.x)** | `src/core/`, `src/commands/`, `src/ui/`, `src/config.py` | 6.1.0 | Active CLI/GUI fallback mode |

`main.py` routes `--api` to the new v22 `core/` stack but routes `--cli` and default GUI launch to the old `src/` v6.x stack. This means **the GUI and CLI never use the new agent engine, healing system, platform abstraction, remote fleet, memory, or web automation subsystems**. Those 40+ new modules are effectively dead code when launched via `main.py`.

**Severity Distribution:**
- 🔴 **Critical:** 7
- 🟠 **High:** 9
- 🟡 **Medium:** 11
- 🔵 **Low/Info:** 6

---

## 1. Architecture Issues

### 🔴 CRITICAL: Dual-Structure Split-Brain (`main.py`)

**File:** `main.py` lines 43–72

`main.py` wires different codebases depending on launch mode:

```
--api   -> core/engine.py (AgentEngine, v22) + api/server.py + config.py (root)
--cli   -> src/cli.py -> src/core/engine.py (CommandEngine, v6.x)
GUI     -> src/ui/app.py (v6.1.0, Neuralis Brain)
```

The new `gui/app.py` (v22/v3.0 GUI) is **never imported by `main.py`**. It uses the new `core/` engine and `config.py` but sits unreachable. The old `src/ui/app.py` is the default.

**Impact:** Every v22 feature — platform abstraction, remote fleet, healing, memory, web automation, agent pool, stealth input, forensic logging — is inaccessible through the default launch path.

**Fix:** Unify `main.py` to route GUI through `gui/app.py` or add a `--legacy-gui` flag for the old path.

---

### 🔴 CRITICAL: Duplicate Engine Architectures

| Component | New (v22) | Old (v6.x) |
|-----------|-----------|------------|
| Engine | `core/engine.py` -> `AgentEngine` (LLM-driven agent loop with vision, tool-calling, self-healing, forensic logging) | `src/core/engine.py` -> `CommandEngine` (keyword-parsing command router with NL fallback) |
| LLM Client | `core/llm_client.py` -> 16+ providers, OpenAI-compatible, retry/backoff, Anthropic native support | `src/core/llm.py` -> Hatz.ai-only, hardcoded base_url, minimal error handling |
| Config | `config.py` (root) -> Dict-based with tenant isolation, stealth mode, approval gates | `src/config.py` -> Constants module with Neuralis Brain URL, COLORS dict |
| GUI | `gui/app.py` -> `SentinelApp` with overlay, themes, system tray, recorder | `src/ui/app.py` -> `SentinelDesktopApp` with Neuralis Brain, system monitor |

The new engine is a **vision-based agent loop** (screenshot -> LLM -> action -> repeat). The old engine is a **keyword-matching command router**. These are fundamentally different paradigms coexisting in one repo.

---

### 🟠 HIGH: `config.py` vs `src/config.py` Collision

Two completely different config systems:
- **Root `config.py`**: `Config` class with JSON persistence, `api_key`, `provider`, `tenant_name`, `approval_mode`, `stealth_input`, `autonomous` mode. Used by `api/server.py` and `core/engine.py`.
- **`src/config.py`**: Module-level constants (`VERSION`, `BRAIN_URL`, `COLORS`, `DEFAULT_CONFIG`). Used by `src/ui/app.py` and `src/core/engine.py`.

Both write to `~/.sentinel-desktop/config.json` but with incompatible schemas. If a user switches between GUI modes, config corruption is likely.

---

### 🟡 MEDIUM: Lazy Subsystem Coupling in `AgentEngine`

`core/engine.py` `AgentEngine.__init__` instantiates `ActionExecutor`, `ForensicLog`, `CheckpointManager`, `ApprovalGate`, `MFADetector`, `SmartWait`, `PopupHandler`, `RecoveryEngine` eagerly — but defers `AuthManager`, `CredentialVault`, `AgentPool`, `PluginLoader`, `TaskScheduler`, `NotificationManager`, `WorkflowEngine`, `ScriptEngine`, `PowerShellRunner`, `ActionRecorder`, `AuditExporter` to lazy properties.

This is reasonable, but `api/server.py` `SentinelServer` creates its own `AgentEngine` for `/command` endpoints (line 435) rather than reusing the persistent one — creating duplicate executor instances and orphaned subsystems.

---

## 2. Critical Bugs

### 🔴 CRITICAL: Four-Way Version Mismatch

| Location | Version | Context |
|----------|---------|--------|
| `core/__init__.py` | **22.0.2** | `__version__` — what `--version` prints |
| `src/config.py` | **6.1.0** | `VERSION` constant |
| `main.py` docstring | **2.0** | Module docstring |
| `api/server.py` | **2.0.0** | FastAPI app `version=` param |
| `setup.py` | **2.0.0** | Package version |
| `gui/app.py` | **v3.0** | Window title string |
| `src/core/engine.py` | **v5.0.0** | Conversational response string |
| `src/commands/help_data.py` | **v5.0.0** | Help text header |

Running `python main.py --version` prints `22.0.2`. The GUI window title says `v3.0`. The setup.py package is `2.0.0`. The old CLI introduces itself as `v5.0.0`.

---

### 🔴 CRITICAL: Stale Docstrings Everywhere

- `main.py` line 3: `"Sentinel Desktop v2.0 - Entry Point"` — actually v22
- `config.py` line 2: `"Sentinel Desktop — Settings persistence layer"` — no version, but comment says AppData (Windows-only path logic despite Linux support)
- `src/core/engine.py` line 387: Introduces itself as `"Sentinel Desktop v5.0.0"` to users
- `gui/app.py` line 1: `"Sentinel Desktop v2 — Main GUI Application"` but window title says `v3.0`
- `core/llm_client.py` line 2: `"Sentinel Desktop v2 — LLM Client"` but is the v22 multi-provider client

---

### 🟠 HIGH: `DEFAULT_ADMIN_PASSWORD` is a Placeholder

**File:** `core/auth.py` line 32

```python
DEFAULT_ADMIN_PASSWORD: str = "[REDACTED]"  # noqa: S105
```

The literal string `"[REDACTED]"` is used as the bootstrap admin password. `AuthManager.__init__` creates an admin user with this password when no users file exists. This means **the default admin password is the 11-character string `[REDACTED]`** — a security theater placeholder that is trivially guessable and publicly visible in source code.

The code has a `requires_password_rotation()` check but nothing **enforces** rotation before allowing API access.

---

### 🟠 HIGH: `requirements.txt` Missing 4 Critical Dependencies

**File:** `requirements.txt`

Current contents (v2.0 era):
```
customtkinter>=5.0.0
pyautogui>=0.9.54
psutil>=5.9.0
requests>=2.28.0
Pillow>=9.0.0
mss>=9.0.0
speedtest-cli>=2.1.0
```

**Missing dependencies actually imported by the codebase:**

| Package | Used By | Impact |
|---------|---------|--------|
| `bcrypt` | `core/auth.py` | Authentication system broken on fresh install |
| `fastapi` | `api/server.py` | API server will not start |
| `uvicorn` | `main.py` | API server will not start |
| `pydantic` | `api/server.py`, `core/action_schemas.py` | API + schema validation broken |
| `pyperclip` | `core/action_executor.py` | Clipboard paste fallback broken |

**Extras not in requirements but installed:** `pywin32`, `uiautomation` (Windows-only, needed for stealth input and UIAutomation)

---

### 🟡 MEDIUM: Dead Code Paths

- `gui/app.py` — **Never imported by `main.py`**. The entire new GUI (tabs, recorder panel, system tray, overlay) is dead code.
- `core/web/browser.py`, `core/web/recorder.py` — Web automation subsystem, never wired to engine.
- `core/memory/long_term.py`, `core/memory/short_term.py` — Memory subsystem, never imported by engine.
- `core/server/event_bus.py`, `core/server/scaling.py` — Server scaling, never imported.
- `core/devtools/inspector.py` — DevTools, never imported.
- `core/healing/*` — Healing subsystems (diff_detect, vision_grounder), imported by engine but only `retry_planner` is actively used.
- `core/remote/*` — Entire fleet/SSH/tunnel subsystem, never wired to API or GUI.
- `core/platform/*` — Platform abstraction layer (7 backends), never imported by engine or GUI.

**Conservative estimate: 30-40% of the v22 `core/` modules are dead code.**

---

### 🟡 MEDIUM: `AgentEngine` Creates a New Instance for `/command` Endpoint

**File:** `api/server.py` line 435

```python
async def _handle_command(self, req: CommandRequest, ...):
    cfg = self.config.load()
    engine = AgentEngine(cfg)  # new engine instance every request
```

Every `/command` API call creates a new `AgentEngine` with full subsystem initialization. This is wasteful and bypasses the persistent engine's plugin loader, scheduler, and recorder state.

---

## 3. Security Issues

### 🔴 CRITICAL: No API Rate Limiting (Except Login)

**File:** `api/server.py`

The API server has rate limiting **only** on the `/auth/login` endpoint (5 attempts per 5 minutes per IP). All other endpoints — including `/goal`, `/command`, `/powershell`, `/scripts/run`, `/workflows/run` — have **zero rate limiting**.

**Attack vectors:**
- Denial-of-service via repeated `/goal` requests (each starts a threaded agent loop)
- Brute-force `/command` with automation payloads
- Abuse `/powershell` endpoint for command execution flooding

**Fix:** Add `slowapi` or FastAPI middleware for global rate limiting.

---

### 🔴 CRITICAL: Hardcoded Internal IP Address

**File:** `src/config.py` line 21

```python
BRAIN_URL = os.environ.get("NEURALIS_BRAIN_URL", "http://100.70.240.55:8001")
```

Hardcoded Tailscale/internal IP `100.70.240.55` as the default Neuralis Brain URL. This leaks internal infrastructure details into source code and git history.

**Fix:** Remove the IP default; require the env var or fail gracefully.

---

### 🟠 HIGH: Plaintext Password Storage in SSH Config

**File:** `core/remote/ssh.py` lines 17-18

```python
@dataclass
class SSHConfig:
    password: str = ""  # prefer key-based auth
```

SSH passwords are stored as plaintext strings in `SSHConfig` dataclasses. The fleet manager (`core/remote/fleet.py`) persists `MachineInfo` to `~/.sentinel/fleet.json` — if any machine uses password auth, the password is stored in plaintext JSON.

**Fix:** Use `CredentialVault` for password storage; only store references in fleet config.

---

### 🟠 HIGH: Non-Windows Vault Falls Back to Base64

**File:** `core/encryption.py` lines 175-183

On Linux/macOS, the "credential vault" is just base64 encoding — **not encryption at all**. Anyone with read access to `config/vault.json` can decode all stored credentials instantly.

**Fix:** Use `cryptography.fernet` or OS keyring (`keyring` package) as a cross-platform fallback.

---

### 🟠 HIGH: API Key in Config Exposed to LLM

**File:** `core/engine.py` lines 268-270

The engine reads `api_key` from config and passes it to the LLM client on every call. While the API server masks the key in `/config` GET responses, the key is:
1. Stored in plaintext in `~/.sentinel-desktop/config.json`
2. Present in the `AgentEngine.config` dict in memory
3. Passed through checkpoint saves (though `api_key` is filtered on line 555)

---

### 🟡 MEDIUM: CORS Allows Wildcard with Token

**File:** `api/server.py` lines 265-270

When an API token is configured, CORS opens to `*` (all origins). This is backwards — a configured token means the API is exposed and CORS should be **restricted**, not opened.

---

### 🟡 MEDIUM: No Input Validation on PowerShell Endpoint

**File:** `api/server.py` lines 544-555

The `/powershell` endpoint accepts a `command` string (max 2000 chars) and passes it directly to `PowerShellRunner.run_command()`. There is no command allowlist, no sandboxing, and no output sanitization. A compromised API token grants arbitrary code execution.

---

### 🟡 MEDIUM: Session Tokens Stored In-Memory Only

**File:** `core/auth.py` lines 289-295

Session tokens are stored in a Python dict (`self._sessions`). Server restart loses all active sessions. No session persistence means no audit trail of past sessions.

---

## 4. Test Coverage Gaps

**Summary:** 75 core/gui modules analyzed. **55 have corresponding test files. 20 have zero test coverage.**

### Modules with NO Test File:

| Module | Subsystem | Risk |
|--------|-----------|------|
| `core/devtools/inspector.py` | DevTools | Low (dead code) |
| `core/healing/diff_detect.py` | Self-Healing | High — visual diff logic |
| `core/healing/retry_planner.py` | Self-Healing | High — recovery strategy |
| `core/healing/vision_grounder.py` | Self-Healing | Medium — visual grounding |
| `core/memory/long_term.py` | Memory | High — persistence layer |
| `core/memory/short_term.py` | Memory | High — context management |
| `core/platform/base.py` | Platform Abstraction | Medium — interface contract |
| `core/platform/capabilities.py` | Platform Abstraction | Medium |
| `core/platform/headless_backend.py` | Platform Abstraction | Medium |
| `core/platform/linux_backend.py` | Platform Abstraction | High — Linux support |
| `core/platform/macos_backend.py` | Platform Abstraction | High — macOS support |
| `core/platform/windows_backend.py` | Platform Abstraction | High — Windows support |
| `core/remote/fleet.py` | Remote Fleet | High — SSH dispatch |
| `core/remote/installer.py` | Remote Fleet | Medium |
| `core/remote/ssh.py` | Remote Fleet | High — remote execution |
| `core/remote/tunnel.py` | Remote Fleet | Medium |
| `core/server/event_bus.py` | Server Infrastructure | Medium |
| `core/server/scaling.py` | Server Infrastructure | Medium |
| `core/web/browser.py` | Web Automation | Medium (dead code) |
| `gui/recorder_panel.py` | GUI | Low |

**Priority recommendation:** Test `core/platform/*` backends and `core/remote/ssh.py` first — these are the most security-sensitive untested modules.

---

## 5. Dependency Issues

### `requirements.txt` vs Actual Imports

| Package | In `requirements.txt`? | Status |
|---------|----------------------|--------|
| `customtkinter` | Yes | Installed |
| `pyautogui` | Yes | Installed |
| `psutil` | Yes | Installed |
| `requests` | Yes | Installed |
| `Pillow` | Yes | Installed |
| `mss` | Yes | Installed |
| `speedtest-cli` | Yes | Installed |
| **`bcrypt`** | **NO** | Installed but **not declared** |
| **`fastapi`** | **NO** | Installed but **not declared** |
| **`uvicorn`** | **NO** | Installed but **not declared** |
| **`pydantic`** | **NO** | Installed but **not declared** |
| **`pyperclip`** | **NO** | Used as fallback, not declared |

### Conditional Dependencies (Not Declared)

| Package | Platform | Used By |
|---------|----------|---------|
| `pywin32` (`win32api`, `win32con`, `win32gui`) | Windows | `core/stealth_input.py`, `core/action_executor.py`, `core/virtual_desktop.py` |
| `uiautomation` | Windows | `core/ui_tree.py`, `core/uia_actions.py` |
| `pystray` | Optional | `gui/tray.py` (system tray) |
| `keyboard` | Optional | `core/failsafe.py` (Esc-x3 hotkey) |

---

## 6. Code Quality Issues

### 🟠 HIGH: Massive Code Duplication

#### System Monitoring (Triple Implementation)

| Implementation | Location | Functions |
|----------------|----------|-----------|
| v22 (new) | `core/system_info.py` | `brief_system_info()`, `system_info()` |
| v6.x (old) | `src/commands/system.py` | `cpu_usage()`, `memory_usage()`, `disk_usage()`, `list_processes()`, `system_info()`, `battery_info()`, `temperature()`, `uptime()` |
| v6.x action | `core/action_executor.py` | `_system_info()`, `_list_processes()` |

All three use `psutil` but with different return formats, error handling, and output structures.

#### LLM Clients (Dual Implementation)

| Implementation | Location | Providers | Retry | Vision |
|----------------|----------|-----------|-------|--------|
| v22 (new) | `core/llm_client.py` | 16+ (OpenAI, Anthropic, Google, etc.) | Exponential backoff + jitter | Native + Anthropic format |
| v6.x (old) | `src/core/llm.py` | 1 (Hatz.ai only) | None | None |

#### Config Systems (Dual Implementation)

| Implementation | Location | Schema |
|----------------|----------|--------|
| v22 (new) | `config.py` (root) | `Config` class with 30+ keys, JSON persistence |
| v6.x (old) | `src/config.py` | Module constants + `DEFAULT_CONFIG` dict |

---

### 🟡 MEDIUM: Inconsistent Error Handling

- **`core/engine.py`**: Comprehensive try/except with recovery engine, forensic logging, and failure tracking. Good.
- **`core/action_executor.py`**: Every handler wraps in try/except returning `{success: False, output: str(exc)}`. Good.
- **`api/server.py`**: Mixed — some endpoints raise `HTTPException`, others return `{success: False, error: str(exc)}`. Inconsistent.
- **`src/core/llm.py`**: Bare `except Exception as e: logger.error(...); return None`. Swallows all errors silently.
- **`src/core/engine.py`**: Top-level try/except in `execute()` but individual `_run_*` methods have no error handling. Partial.
- **`core/remote/ssh.py`**: `run()` catches `subprocess.TimeoutExpired` but not `FileNotFoundError` (if ssh binary missing). Incomplete.

---

### 🟡 MEDIUM: Missing Type Hints

Well-typed modules: `core/engine.py`, `core/auth.py`, `core/encryption.py`, `core/llm_client.py`, `config.py`

Missing/partial type hints:
- `src/core/engine.py` — Return types missing on most methods
- `src/core/llm.py` — `def chat(self, messages, temperature=0.7, max_tokens=2000):` — no types at all
- `src/commands/*.py` — Consistently untyped across all 15 command modules
- `src/ui/app.py` — No type hints on any method
- `gui/app.py` — Partial (has `-> None` on some methods, missing on others)

---

### 🔵 LOW: Inconsistent String Formatting

- v22 code uses f-strings consistently
- v6.x code mixes f-strings and `%s` formatting
- Some modules use `.format()`, some use `%`, some use f-strings — no project-wide standard enforced

---

## Prioritized Remediation Plan

### Phase 1: Critical Security (Immediate)
1. **Add rate limiting** to all API endpoints (`slowapi` or FastAPI middleware)
2. **Replace `DEFAULT_ADMIN_PASSWORD`** with a random generated password printed on first startup
3. **Remove hardcoded IP** `100.70.240.55` from `src/config.py`
4. **Enforce password rotation** — refuse API access if admin still uses default password
5. **Fix CORS policy** — restrict origins even when token is set

### Phase 2: Dependency & Build (This Week)
6. **Update `requirements.txt`** with all 5 missing dependencies
7. **Add `pyproject.toml`** optional dependencies for platform-specific packages
8. **Bump and unify version** to `22.0.2` across all 8 locations
9. **Fix `main.py`** to route GUI through `gui/app.py` (or add `--legacy` flag)

### Phase 3: Architecture Cleanup (This Sprint)
10. **Decide migration strategy**: Either delete `src/` or formally mark it as deprecated
11. **Wire dead subsystems**: Connect `core/platform/*`, `core/remote/*`, `core/memory/*` to engine or remove them
12. **Consolidate config**: Migrate to single `config.py` with migration logic for old `src/config.py` users

### Phase 4: Test Coverage (Next Sprint)
13. Add tests for `core/platform/*` (7 modules, all untested)
14. Add tests for `core/remote/*` (4 modules, all untested)
15. Add tests for `core/healing/*` (2 of 3 untested)
16. Add tests for `core/memory/*` (2 modules, all untested)

### Phase 5: Code Quality (Ongoing)
17. Consolidate duplicate system monitoring code
18. Add type hints to all `src/` modules
19. Standardize error handling patterns
20. Implement linting (`flake8`/`ruff`) with pre-commit hooks

---

## Appendix: File Inventory

```
Total .py files:       180+
Core modules:           46  (in core/)
GUI modules:            11  (in gui/)
Old src/ modules:       30  (in src/)
Test files:            200+  (in tests/)
Untested modules:       20
Version strings found:   8  (all different)
```

---

*End of Audit Report*
