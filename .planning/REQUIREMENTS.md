# Requirements: Sentinel Desktop v8.0.0 Webhand

**Defined:** 2026-06-06
**Core Value:** Automate any Windows desktop task through natural language — safely, reliably, and with full visibility.

## v8 Requirements

### Browser Core

- [x] **WEB-01**: Embedded controlled browser via Playwright (Chromium/Firefox/WebKit) with CDP — launches a managed browser instance the agent drives directly
- [x] **WEB-02**: `web_open` action — navigate to a URL in the managed browser, handles redirects and page load events
- [x] **WEB-03**: `web_click` action — click elements by CSS selector, text content, or ARIA role; auto-scrolls element into view
- [x] **WEB-04**: `web_type` action — type text into form fields identified by selector, label, or placeholder; clears existing content by default
- [x] **WEB-05**: `web_read` action — extract text content from the full page or a specific element by selector
- [x] **WEB-06**: `web_extract` action — extract structured data (HTML tables → JSON, lists, form values, page metadata)

### Browser Advanced

- [x] **WEB-07**: `web_wait_for` action — wait for element visibility, navigation complete, network idle, or specific text on page
- [x] **WEB-08**: `web_screenshot` action — capture browser viewport or element screenshot as PIL Image
- [x] **WEB-09**: `web_eval_js` action — execute arbitrary JavaScript in browser context and return result
- [x] **WEB-10**: `web_download` action — download files from browser with progress tracking
- [x] **WEB-11**: `web_upload` action — upload files to web forms by setting file input elements
- [x] **WEB-12**: `web_tabs` action — list open tabs, switch between tabs, create new tabs, close tabs

### Dual-Mode Unification

- [x] **DUAL-01**: Engine auto-detects whether the target is a web app or native desktop and routes to browser DOM mode or native vision mode accordingly
- [x] **DUAL-02**: Mid-task handoff — agent can download a file in the browser, then open it natively (browser → native transition)

### Appliance UX & Sessions

- [x] **CERT-01**: Auto-accept self-signed certificate warnings for explicitly whitelisted appliance hostnames only (configurable whitelist)
- [x] **CERT-02**: Login form detection — recognize common IT admin login pages (SonicWall, FortiGate, UniFi, Meraki, etc.) and offer to fill credentials
- [x] **SESS-01**: Session vault — save cookies + localStorage per site, encrypted via core/encryption.py
- [x] **SESS-02**: Session vault restore — reload saved cookies on return visits so the agent doesn't re-login every run

### Web Recorder

- [x] **REC-01**: Web recorder captures browser interactions (navigations, clicks, form fills) into replayable Sentinel script JSON format

## Out of Scope

| Feature | Reason |
|---------|--------|
| SSH/network device control | v9.0 "Netops" |
| Fleet/daemon mode | v10.0 "Sentinel Server" |
| Persistent memory / RAG | v11.0 "Memory" |
| Multi-agent orchestration | v12.0 "Conductor" |
| Browser extension install | Not needed for DOM control |
| Visual regression testing | Not core to IT automation |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| WEB-01 | Phase 1 | ✅ Complete |
| WEB-02 | Phase 1 | ✅ Complete |
| WEB-03 | Phase 1 | ✅ Complete |
| WEB-04 | Phase 1 | ✅ Complete |
| WEB-05 | Phase 1 | ✅ Complete |
| WEB-06 | Phase 2 | ✅ Complete |
| WEB-07 | Phase 2 | ✅ Complete |
| WEB-08 | Phase 2 | ✅ Complete |
| WEB-09 | Phase 2 | ✅ Complete |
| WEB-10 | Phase 2 | ✅ Complete |
| WEB-11 | Phase 2 | ✅ Complete |
| WEB-12 | Phase 2 | ✅ Complete |
| DUAL-01 | Phase 3 | ✅ Complete |
| DUAL-02 | Phase 3 | ✅ Complete |
| CERT-01 | Phase 3 | ✅ Complete |
| CERT-02 | Phase 3 | ✅ Complete |
| SESS-01 | Phase 4 | ✅ Complete |
| SESS-02 | Phase 4 | ✅ Complete |
| REC-01 | Phase 4 | ✅ Complete |

**Coverage:**
- v8 requirements: 19 total
- Mapped to phases: 19
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-06*
*Last updated: 2026-06-06 after initial definition*
