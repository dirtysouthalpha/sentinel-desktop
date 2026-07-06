# Sentinel Desktop v26.0.0 — SPEC

## Scope
Four major enterprise features delivered in one release.

### Feature 1: Plugin Marketplace
- New module: `core/marketplace.py`
- API endpoints: GET /marketplace/list, POST /marketplace/install, DELETE /marketplace/{name}
- Plugin registry: JSON catalog of community plugins with metadata
- Install flow: download -> validate -> extract to plugins/ -> reload
- Uninstall flow: stop plugin -> remove files -> reload

### Feature 2: Multi-Tenant Web Dashboard
- New module: `core/dashboard.py` (enhanced)
- Static web UI: `dashboard/` directory with HTML/CSS/JS
- API endpoints: GET /dashboard, GET /dashboard/agents, GET /dashboard/metrics
- Real-time agent monitoring via WebSocket
- Per-tenant isolation using existing tenant_name config

### Feature 3: Telemetry & Analytics
- New module: `core/telemetry.py`
- Track: agent runs, step counts, success rates, action types, latency
- API endpoints: GET /telemetry, GET /telemetry/summary
- Opt-in only via config flag
- SQLite storage for historical data

### Feature 4: Deep Legacy Migration
- Migrate unique src/ functionality into core/
- src/commands/ -> core/commands/ (consolidate)
- src/core/brain.py -> core/brain.py (Neuralis integration)
- src/cli.py -> core/cli.py
- Remove src/ directory entirely
- Update all imports and entry points

## Boundaries (NOT building)
- No new GUI features (GUI is thin wrapper)
- No new LLM providers
- No new platform backends
- No database migrations beyond telemetry SQLite

## Acceptance Criteria
1. All existing tests pass after legacy migration
2. New marketplace endpoints functional and tested
3. Dashboard serves static HTML at /dashboard
4. Telemetry records and retrieves metrics
5. No remaining src/ imports in core/ or gui/ or api/
6. Version unified to 26.0.0

## Estimated Complexity
- Feature 4 (Legacy Migration): HIGHEST — touches every import path
- Feature 3 (Telemetry): MEDIUM — self-contained module + SQLite
- Feature 1 (Marketplace): MEDIUM-HIGH — download/validate/install flow
- Feature 2 (Dashboard): MEDIUM — mostly static files + API endpoints
