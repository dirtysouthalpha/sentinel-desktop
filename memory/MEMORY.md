# Memory Index

- [current-project-status](current-project-status.md) — Sentinel Desktop v22.0 "Aria": production-ready with 9,159 passing tests, zero lint errors, all v18-v22 features complete; currently at Phase 3a (PyPI Trusted Publishing requires manual user configuration)
- [grind-backlog-priority](grind-backlog-priority.md) — The real priority queue is GRIND-BACKLOG.md driven by autonomous grind-phase.sh loop; currently blocked at Phase 3a awaiting manual PyPI configuration
- [grind-loop-protocol](grind-loop-protocol.md) — Grind loop works top-down through GRIND-BACKLOG.md; does one phase per session with clean context; if active phases empty, runs maintenance pass
- [v22-quality-gates](v22-quality-gates.md) — v22.0 quality gates all passed: 9,159 tests passing, 153 skipped, zero lint errors (ruff check clean), all deliverables committed
- [test-timeout-fix-2026-07-13](test-timeout-fix-2026-07-13.md) — Fixed test timeout failure by patching memory_tab.MemoryTab in test fixture; test now passes in 0.08s instead of timing out
- [maintenance-pass-2026-07-13](maintenance-pass-2026-07-13.md) — Maintenance pass results: discovered and fixed test timeout, all quality gates verified green, ready for PyPI configuration
