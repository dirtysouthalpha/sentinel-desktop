---
name: test-timeout-fix-2026-07-13
description: Fixed test timeout failure in test_open_settings by patching MemoryTab
metadata:
  type: feedback
---

# Test Timeout Fix (2026-07-13)

## Issue
The test `test_open_settings` in `tests/test_app.py::TestSettingsHooks` was timing out (>10s) when run as part of the full test suite, but passed when run individually.

## Root Cause
The `memory_tab.MemoryTab` class was not being patched in the `_make_app` test fixture. When the app initialized during the test, it tried to instantiate the real `MemoryTab` class, which expects actual tkinter widgets but was receiving `_FakeText` stubs instead. This caused a deadlock during the `_refresh_facts()` call when the memory tab tried to configure text widgets.

## Fix
Added `patch("gui.tabs.memory_tab.MemoryTab", MagicMock())` to the `_make_app` fixture in `tests/test_app.py`, alongside the existing patches for other tab classes (scripts_tab, workflows_tab, history_tab, settings_tab).

## Files Changed
- `tests/test_app.py` — Added memory_tab.MemoryTab patch to test fixture

## Result
- Test now passes in 0.08s instead of timing out
- All quality gates green: 9,159 passing, 153 skipped, 0 failed
- Lint clean
- Committed and pushed (commit 65ca94c)

## Why This Matters
Test fixtures must patch ALL external dependencies that expect real framework widgets. The memory_tab was accidentally omitted from the original fixture setup, causing intermittent failures depending on test order.

## Related
- `tkinter-test-stub-pollution.md` — concept about why GUI except-branch tests need self-consistent fake tkinter
