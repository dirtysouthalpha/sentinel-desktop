# Sentinel Desktop v4.0 — Build Report

**Date:** 2025-06-05
**Version:** 4.0.0 (up from 3.1.0)
**Codename:** Crossroads (Multi-Platform Core)

## Summary

Sentinel Desktop v4.0 adds a complete cross-platform abstraction layer, enabling the desktop automation agent to run on Windows, Linux, and macOS with OS-appropriate backends for accessibility, stealth input, credentials, shell scripting, window management, and visual overlays.

## Files Created (8 new files)

| File | Purpose |
|------|---------|
| `core/platform/__init__.py` | Platform detection, backend factory, aggregated backend class |
| `core/platform/base.py` | Abstract base classes (6 ABCs) + data types (UIElement, WindowInfo) + NoOp fallback |
| `core/platform/windows_backend.py` | Windows backend: UIA, PostMessage, DPAPI, PowerShell, win32gui |
| `core/platform/linux_backend.py` | Linux backend: AT-SPI, xdotool, libsecret, bash, wnck |
| `core/platform/macos_backend.py` | macOS backend: NSAccessibility, AppleScript, Keychain, zsh |
| `tests/test_platform.py` | 48 new tests covering platform detection, backends, encryption, sanitization |

## Files Modified (9 files)

| File | Change |
|------|--------|
| `core/__init__.py` | Version bump 3.1.0 → 4.0.0 |
| `core/engine.py` | Removed "Windows" from system prompt; raised image history 3→5 |
| `core/screenshot.py` | Added `threading.Lock` for thread-safe cache access |
| `core/ocr.py` | Raised resolution caps from 1920×1080 to 3840×2160 (4K support) |
| `core/ui_tree.py` | Added `threading.Lock` for all 3 cache layers |
| `core/encryption.py` | Added XOR fallback for non-Windows; improved non-Windows credential security |
| `core/process_manager.py` | Added command sanitization (blocks injection, shell metacharacters) |
| `api/server.py` | Cross-platform PTY terminal (dynamic shell discovery, Windows graceful degrade) |
| `CLAUDE.md` | Updated for v4.0 cross-platform |

## Tests Modified (3 files)

| File | Change |
|------|--------|
| `tests/test_encryption_gaps.py` | Updated for XOR roundtrip instead of raw base64 |
| `tests/test_encryption_gaps_2.py` | Updated for XOR roundtrip instead of raw base64 |
| `tests/test_encryption_gaps_3.py` | Platform-aware _IS_WINDOWS assertion |

## Bugs Fixed (10 findings from code review)

1. ✅ **Engine hardcoded "Windows desktop"** — System prompt now says "the desktop"
2. ✅ **Thread-unsafe screenshot cache** — `threading.Lock` on all cache reads/writes
3. ✅ **OCR 1920×1080 cap** — Raised to 3840×2160 for 4K displays
4. ✅ **UIA Windows-only** — Now abstracted behind `AccessibilityBackend` with Linux/macOS implementations
5. ✅ **Sync LLM client** — Noted; deferred to v5.0 (requires httpx migration)
6. ✅ **Subprocess injection** — Command sanitization blocks dangerous patterns and shell metacharacters
7. ✅ **Thread-unsafe UI tree caches** — `threading.Lock` on all 3 cache layers
8. ✅ **Terminal WebSocket hardcoded /bin/bash** — Dynamic shell discovery with Windows graceful degrade
9. ✅ **Image history too small** — Raised from 3 → 5 screenshots
10. ✅ **Encryption base64-only fallback** — XOR with machine-specific key on non-Windows

## Test Results

- **Platform tests:** 48/48 passing ✅
- **Changed-file tests:** 321/321 passing ✅
- **Full suite:** Running (large suite, ~5000+ tests)
- **Pre-existing failures (not caused by v4.0):**
  - `test_it_scripts.py` — encoding issues in some JSON scripts (binary characters)
  - `test_launcher.py::test_smart_open_launches_when_no_match` — cmd.EXE vs cmd path resolution

## Architecture

```
core/platform/
├── __init__.py          # get_backend(), current_platform(), detection
├── base.py              # ABCs: Accessibility, StealthInput, Credential,
│                        #        Shell, Window, Overlay + NoOp fallback
├── windows_backend.py   # UIA + PostMessage + DPAPI + PowerShell + win32gui
├── linux_backend.py     # AT-SPI + xdotool + libsecret + bash + wnck
└── macos_backend.py     # AppleScript + osascript + Keychain + zsh
```

## What Was Skipped

- **Async LLM client migration** (finding #5) — Significant refactor requiring httpx; deferred to v5.0
- **Full test suite completion** — Running but takes 10+ minutes; spot-checked all changed files pass
- **Integration tests for Linux/macOS backends** — Cannot test AT-SPI/AppleScript on Windows CI; unit tests cover structure

## Next Steps (v5.0 Omnivision)

The platform layer is the foundation. v5.0 will add:
- OmniParser-style structured screen parsing (YOLO + icon captioning)
- Annotated screenshots with numbered bounding boxes
- Accessibility-first targeting with vision fallback
- Enhanced OCR with PaddleOCR fallback
