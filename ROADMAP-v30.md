# Sentinel Desktop — ROADMAP to v30.0.0

**Created:** 2026-07-05  
**Current Version:** v26.0.0  
**Target:** v30.0.0  
**Releases:** 4 major versions

---

## v27.0.0 — Deep Architecture & Performance

**Theme:** Kill the legacy, optimize the core.

### 1. Full Legacy Migration (src/ → core/)
- Migrate `src/commands/` → `core/commands/` (13 command modules)
- Migrate `src/core/brain.py` → `core/brain.py` (Neuralis integration)
- Migrate `src/core/llm.py` → merge into `core/llm_client.py`
- Migrate `src/cli.py` → `core/cli.py`
- Delete `src/` directory entirely
- Rewrite all 20+ test imports from `src.*` → `core.*`
- Update `main.py` to remove `--legacy-gui` flag
- Update `setup.py` entry points

### 2. Plugin Sandboxing
- New module: `core/sandbox.py`
- Execute community plugins in isolated subprocess with resource limits
- Plugin permission model: `permissions: ["clipboard", "screenshot", "network"]`
- Timeout enforcement (30s default per plugin call)
- Memory cap via `resource.setrlimit`

### 3. Performance Optimization
- Profile `AgentEngine.run()` loop with `cProfile`
- Add async screenshot capture (non-blocking)
- Implement action batching for consecutive clicks/types
- Cache OCR results when screenshot is unchanged
- Lazy-load platform backends (only import active OS backend)

### 4. New Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/sandbox/status` | GET | Active sandboxed plugins |
| `/sandbox/kill/{pid}` | POST | Kill a sandboxed plugin |

### Acceptance Criteria
- [ ] Zero `from src.` imports remain in entire codebase
- [ ] `src/` directory deleted
- [ ] All 200+ existing tests pass after migration
- [ ] Plugin sandbox executes sample plugin in subprocess
- [ ] Profiling benchmarks recorded before/after optimization

---

## v28.0.0 — Multi-Agent Orchestration & AI Enhancement

**Theme:** Swarm intelligence, persistent memory, smarter vision.

### 1. Multi-Agent Swarm Mode
- New module: `core/swarm.py`
- Coordinate N AgentEngine instances on parallel tasks
- Task queue with priority and dependency graph
- Inter-agent communication via shared message bus
- Swarm status dashboard panel
- API endpoints:
  - `POST /swarm/create` — create a swarm with N agents
  - `POST /swarm/{id}/assign` — assign task to swarm
  - `GET /swarm/{id}/status` — swarm progress
  - `POST /swarm/{id}/stop` — stop entire swarm

### 2. Persistent Vector Memory
- Replace `core/memory/long_term.py` with vector-backed store
- Embed agent experiences using sentence-transformers
- Recall relevant past solutions when agent encounters similar goals
- New module: `core/memory/vector_store.py`
- Storage: ChromaDB or FAISS local index
- API endpoint: `GET /memory/search?q=...`

### 3. LLM Streaming Responses
- Stream LLM tokens to dashboard via WebSocket
- Real-time "agent thinking" display in web UI
- Update `core/llm_client.py` to support `stream=True`
- Update dashboard to show streaming reasoning

### 4. Advanced Vision Pipeline
- Template matching for repeated UI elements
- OCR + vision fusion (combine LLM vision with pytesseract OCR)
- Element anchoring (track elements across screenshots)
- Confidence scoring on vision detections
- New module: `core/vision/pipeline.py`

### Acceptance Criteria
- [ ] Swarm of 3+ agents can execute independent tasks simultaneously
- [ ] Vector memory returns relevant past experience for similar goals
- [ ] LLM streaming visible in dashboard within 1s of first token
- [ ] Vision pipeline correctly identifies UI elements with 80%+ accuracy

---

## v29.0.0 — Enterprise Cloud & Scalability

**Theme:** Production deployment, distributed fleets, real-time everything.

### 1. Distributed Fleet with Redis
- New module: `core/fleet/redis_bus.py`
- Replace in-memory agent pool with Redis-backed distributed queue
- Agents on multiple machines share work via Redis pub/sub
- Fleet manager API for remote agent provisioning
- Health monitoring across fleet nodes
- Endpoints:
  - `GET /fleet/nodes` — list all fleet nodes
  - `POST /fleet/deploy` — deploy agent to remote node
  - `GET /fleet/health` — aggregate fleet health

### 2. WebSocket Telemetry Streaming
- Real-time metrics push to dashboard (replacing 10s polling)
- Live action feed: every click, type, screenshot streamed live
- Historical replay: scrub through past agent runs
- Update dashboard with WebSocket connection

### 3. Role-Based Plugin Permissions
- Plugin manifests declare required permissions
- Admin must approve permissions on install
- Marketplace shows permission badges
- Sandboxed plugins denied access without explicit grant
- Config: `plugin_permissions: {"weather-check": ["network", "screenshot"]}`

### 4. Kubernetes Deployment
- Helm chart for Sentinel Desktop deployment
- Horizontal Pod Autoscaler config
- Persistent volume for telemetry SQLite
- Ingress with TLS termination
- Health probe configuration (liveness/readiness)
- New directory: `deploy/k8s/`

### Acceptance Criteria
- [ ] Two Sentinel instances share work via Redis bus
- [ ] Dashboard receives telemetry updates within 500ms
- [ ] Plugin install requires permission approval
- [ ] Helm chart deploys to minikube successfully

---

## v30.0.0 — Intelligence & Final Polish

**Theme:** Self-improving agent, natural language workflows, voice control, final release.

### 1. Self-Improving Agent
- Agent analyzes its own run history (from telemetry)
- Identifies repeated failure patterns and auto-adjusts strategy
- Success/failure classifier on actions
- Auto-generated "playbooks" for common goals
- New module: `core/learning/playbook.py`
- Endpoint: `GET /playbooks` — list learned playbooks

### 2. Natural Language Workflow Builder
- Describe a multi-step workflow in plain English
- LLM generates a workflow JSON automatically
- User can review, edit, and save
- Execute generated workflows like recorded ones
- New endpoint: `POST /workflows/generate` — AI-generated workflow

### 3. Voice Control Integration
- Speech-to-text input for agent goals
- Text-to-speech output for agent status updates
- Wake word detection ("Hey Sentinel")
- New module: `core/voice/control.py`
- Uses Whisper for STT, pyttsx3 for TTS
- Endpoint: `POST /voice/goal` — start agent from voice input

### 4. Final Audit, Documentation & Release
- Full security audit (input fuzzing, penetration test)
- API documentation via OpenAPI/Swagger auto-generation
- User manual (PDF generation)
- Performance benchmarks vs v22 baseline
- Final test count target: 300+ tests
- Migration guide for v22 → v30 users
- `RELEASE_NOTES-v30.md`

### Acceptance Criteria
- [ ] Agent applies learned playbook to similar goal without re-exploration
- [ ] NL workflow builder generates valid workflow from description
- [ ] Voice control starts agent with spoken goal
- [ ] OpenAPI spec generated automatically at `/docs`
- [ ] Full test suite passes (300+ tests)
- [ ] Security audit complete with no critical findings

---

## Release Timeline

| Version | Theme | New Modules | New Endpoints | New Tests |
|---------|-------|-------------|---------------|-----------|
| **v27** | Architecture & Performance | `sandbox.py`, `commands/*` | 2 | ~20 |
| **v28** | Swarm & AI Enhancement | `swarm.py`, `vector_store.py`, `vision/pipeline.py` | 6 | ~25 |
| **v29** | Enterprise Cloud & Scale | `fleet/redis_bus.py`, `deploy/k8s/` | 3 | ~15 |
| **v30** | Intelligence & Polish | `learning/playbook.py`, `voice/control.py` | 3 | ~20 |
| **TOTAL** | | 8+ new modules | 14 endpoints | ~80 tests |

---

## Dependency Graph

```
v26 (current)
  │
  ▼
v27 — Legacy Migration + Sandboxing
  │    (must complete before v28 — clean codebase needed)
  ▼
v28 — Swarm + Vector Memory + Vision
  │    (builds on clean core, adds AI capabilities)
  ▼
v29 — Redis Fleet + K8s + Real-time
  │    (scales v28 features across multiple nodes)
  ▼
v30 — Self-learning + Voice + Final Release
       (polish layer on top of everything)
```

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Legacy migration breaks imports | HIGH | Run tests after each file move, batch small |
| Plugin sandbox subprocess overhead | MEDIUM | Benchmark before/after, opt-in only |
| Redis dependency adds complexity | MEDIUM | Keep in-memory fallback for single-node |
| Vector store adds heavy deps | MEDIUM | Make optional, lazy-import |
| K8s manifests become stale | LOW | CI test with minikube |
