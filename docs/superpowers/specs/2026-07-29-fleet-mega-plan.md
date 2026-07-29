# Fleet Mega-Plan — All Remaining Workstreams

**Date:** 2026-07-29
**Scope:** 6 workstreams (A–F) covering deployment, expansion, integration, fixes, vNext upgrade, and self-improvement.
**Principle:** Deploy the foundation first (live fleet), then expand (PremierBot), then integrate (empire), then evolve (vNext + self-improvement).

---

## Current Fleet State (verified 2026-07-29)

| Node | Role | Status | Git | Notes |
|------|------|--------|-----|-------|
| NUKE `100.86.200.42` | CNS (:4433) | ✅ Running (systemd) | `afca3f5` (latest) | Hosts composio + sentinel MCP hubs |
| homeserver `100.70.240.55` | PRIME (:4434) | ⚠️ SentinelMesh Running but on OLD code `0102ac1` | 10 commits behind | Needs git pull + restart |
| PremierBot `100.89.53.128` | Available | ⛔ SSH key not authorized | — | Needs one-time human action for SSH |
| hackbox `100.115.63.94` | Edge | ❌ Offline 3+ days | — | Self-converges when powered on |

**Incidents found this session:**
- SentinelMesh service was **PAUSED** on homeserver (now Started, but old code)
- Sentinel MCP proxy session dropped ("Session not found") — proxy fragility issue

---

## Workstream A — Deploy Phase 6 to Homeserver + Live Cross-Node Task

**Goal:** Run Phase 6 code on the live fleet and prove cross-node execution works for real.

### Steps:
1. `git pull origin main` on homeserver (10 commits: `0102ac1` → `afca3f5`)
2. Restart SentinelMesh NSSM service
3. Verify homeserver mesh node comes up on :4434 with Phase 6 code
4. From NUKE, connect to homeserver mesh node as peer
5. Deploy a real shell task (e.g., `echo fleet-mesh-live`) from NUKE → homeserver
6. Verify TASK_COMPLETED comes back with correct stdout
7. Run `fleet/status` and confirm both nodes visible

### Blocker: Sentinel MCP session currently down — retry connection before proceeding.

---

## Workstream B — Add PremierBot as 3rd Mesh Node

**Goal:** PremierBot (`pn-bcw5w54`, `100.89.53.128`) joins the mesh as a worker node.

### Steps:
1. Resolve SSH access (human action needed: add NUKE's SSH key to PremierBot)
2. Deploy mesh agent to PremierBot (install Python deps, copy mesh code)
3. Configure as DESKTOP-priority worker node with `can_execute_desktop=True`
4. Connect to NUKE mesh node as peer
5. Verify three-node mesh: NUKE (CNS) ↔ homeserver (PRIME) ↔ PremierBot (DESKTOP)
6. Deploy a test task to PremierBot, verify execution + metrics

### Dependencies: SSH access to PremierBot (currently blocked — key not authorized).

---

## Workstream C — Empire × Mesh Integration

**Goal:** Wire the real empire (Raven, Buffer, YT analytics, Alpaca P&L) as mesh-orchestrated plans that produce real outcomes.

### Current state:
- Phase 6C created generic empire-plan tasks (yt-stats, alpaca-pnl, buffer-metrics, empire-score, narrative)
- Real empire services exist on homeserver (sentinel-prime-premium dashboard)
- No live wiring between mesh tasks and empire APIs

### Steps:
1. Create `EmpireTaskHandler` — maps empire task types to real API calls:
   - `yt-stats` → YouTube Analytics API (views, subs, watch time)
   - `alpaca-pnl` → Alpaca paper trading API (positions, unrealized P&L)
   - `buffer-metrics` → Buffer API (posts, impressions, engagement)
   - `empire-score` → aggregate scoring function
   - `narrative` → LLM summary of metrics
2. Register handler in `TaskExecutor` as a new task type category
3. Add empire plan templates to `Orchestrator` (daily briefing, weekly report, trade review)
4. Create `tests/test_empire_live.py` — tests with mocked empire APIs
5. Wire empire metrics into `FleetMetricsAggregator` for dashboard display
6. End-to-end: create empire plan → execute across mesh → verify all 5 task types complete

---

## Workstream D — Fix `test_legacy_engine.py` ✅ DONE

**Root cause:** `_is_complex_task("go home after that")` used `" after that "` (with trailing space) which doesn't match end-of-string.

**Fix:** Pad `t` with spaces (`f" {text.lower()} "`) and add leading space to `" first "` indicator. Also use original (unpadded) text for the comma-count check.

**Result:** 22/22 tests pass.

---

## Workstream E — vNext 7-Phase Upgrade Plan

**Goal:** Fleet-wide capability upgrade across all components.

### Phase 1 — Desktop v30 → v31 Unified
- Port v22 hardening + tests into mainline
- Unified GUI decision: keep customTkinter or migrate
- Target: all 191+ mesh tests pass on both platforms

### Phase 2 — CLI 3.2 → 1.0 GA
- ROADMAP-V2 parity: Claude Code / Warp feature parity (V1–V10)
- Subcommand completeness: all mesh operations via CLI
- Shell completion, man pages, `--help` polish

### Phase 3 — CNS 0.6 → 1.0
- Complete 7-phase CNS roadmap
- Run live headless for 7 days without intervention
- Self-healing verified: crash → restart → resume < 30s

### Phase 4 — Neuralis Recall 67% → 85%+
- Embedding-based semantic search (replace keyword `search()`)
- Golden eval suite: 12 queries, 85%+ recall bar
- Restore drills: backup → wipe → restore → verify

### Phase 5 — Gateway Proxy 7 → 8 + MCP 12 → 13
- Proxy: add empire-aware routing, rate limiting, circuit breaker
- MCP: add `empire_refresh` tool (13th tool)
- Hardening: auth refresh, connection pooling, graceful degradation

### Phase 6 — CAPSTONE: Prime ↔ Neuralis ↔ CNS Unified Orchestration
- Single control plane across all three
- Empire plans → mesh execution → brain memory → dashboard display
- Full loop proven with live data

### Phase 7 — Fleet-Wide Observability + Golden Evals
- Per-component golden eval suites (mesh, empire, brain, CLI, CNS)
- Automated daily eval runs + trend tracking
- Alert on regression (recall drop, test failure, latency spike)

---

## Workstream F — Self-Improvement Loop

**Goal:** Fleet audits its own code, finds gaps, proposes upgrades, executes them autonomously (within trust dial).

### Architecture:
1. **Auditor** — scans codebase for:
   - Untested code paths
   - Missing error handling
   - Stale TODOs / FIXMEs
   - API mismatches (like the `_is_complex_task` bug)
2. **Proposer** — converts audit findings into prioritized task proposals
3. **Executor** — implements proposals within trust dial (SAFE actions auto-execute, DESTRUCTIVE propose)
4. **Verifier** — runs tests, checks the fix, closes the loop
5. **Reporter** — daily digest of what was found, proposed, executed, verified

### Steps:
1. Create `core/mesh/self_improvement.py` — Auditor + Proposer + Executor + Verifier
2. Implement code scanning: AST-based gap detection
3. Implement proposal generation: finding → task → priority
4. Implement execution: trust-dial-gated implementation
5. Wire into existing `watcher.py` / `digest_scheduler.py` for periodic runs
6. Create `tests/test_self_improvement.py`
7. Run first full audit → produce improvement plan

---

## Execution Order

```
A (deploy — foundation) → D (quick fix → DONE) → C (empire code) → B (PremierBot) → E (vNext phases) → F (self-improvement)
```

A must come first (live fleet needs Phase 6). D is done. C can proceed in parallel with A recovery. B needs SSH access. E and F are longer-term and build on A–C.

---

## Audit Criteria

- [ ] A: NUKE → homeserver cross-node task succeeds, `fleet/status` shows 2 nodes
- [ ] B: Three-node mesh test passes, PremierBot executes a task
- [ ] C: Empire plan with 5 task types completes end-to-end (mocked APIs)
- [ ] D: 22/22 legacy engine tests pass ✅
- [ ] E: Each phase has a design doc + implementation plan + tests
- [ ] F: First audit produces ≥3 actionable findings, ≥1 auto-executed fix
- [ ] Overall: all existing 191 tests still pass + new tests for C and F
