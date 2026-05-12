# Sentinel Desktop v3.0 — Epic Work Edition

> **Goal:** Make Sentinel Desktop a tool you actually use daily — at work AND at home. 
> Professional-grade IT automation that your coworkers would beg to use.

## Problem Statement

v2.x is a solid technical foundation (12,947 lines, 55 files, 37 actions) but it's still a **tech demo**:
- No script recording/playback — you have to describe everything in English
- No reusable workflows — same task repeated = same prompt repeated
- No web dashboard — GUI requires RDP into the server
- No scheduled/triggered runs — can't queue "run this at midnight"
- No multi-agent — can't run 2 tasks simultaneously
- Not portable — coworkers can't install it easily
- No audit reporting — forensic log exists but no manager-friendly export

## v3.0 Feature Roadmap

### 🏢 WORK MODE — IT Support Arsenal

**3.1 Script Recorder & Playback** *(HIGH — money feature)*
- Record mode: watch user actions, capture as editable JSON script
- Auto-translate recorded scripts to natural language descriptions
- One-click replay: "Run the password reset script"
- Script library: save, tag, search, share scripts
- Parameterize scripts: "Reset password for {username}" with prompts
- Files: `core/recorder.py`, `core/script_engine.py`, `gui/recorder_panel.py`

**3.2 Workflow Builder** *(HIGH — repeatable automation)*
- Chain scripts into multi-step workflows
- Conditions: "If Excel says 'Error', run fix script, else continue"
- Loops: "Do this for every user in the list"
- Variables: pass outputs between steps
- Schedule: "Run this workflow every Monday at 8am"
- Files: `core/workflow.py`, `core/scheduler.py`, `gui/workflow_editor.py`

**3.3 IT Support Quick Actions** *(HIGH — instant value)*
- Pre-built scripts for common IT tasks:
  - Password reset (Active Directory)
  - Account unlock
  - Disk cleanup & temp file removal
  - Network diagnostics (ping, traceroute, DNS lookup)
  - Service restart (by name)
  - Event log scanning (errors in last hour)
  - Software inventory export
  - Printer queue clear
  - Driver update check
  - System restore point creation
- One-click from system tray or command palette
- Files: `scripts/it_support/` directory with categorized .json scripts

### 🖥️ WEB DASHBOARD *(MEDIUM — professional interface)*

**3.4 Browser-Based Control Center**
- React/Vite dashboard served from the API server
- Live screen view with click-to-act
- Run history with replay
- Script library browser
- Workflow editor (drag & drop)
- Real-time log streaming (WebSocket)
- Multi-machine dashboard (connect to multiple Sentinel Desktop instances)
- Files: `web/` directory with React app, `api/static.py` to serve it

### 🔌 EXTENSIBILITY

**3.5 Plugin System** *(MEDIUM — let others extend)*
- Plugin directory: drop a .py file, it auto-loads
- Plugin API: register custom actions, menu items, settings
- Built-in plugin examples: Active Directory, PowerShell runner, SSH tunnel manager
- Plugin marketplace concept (local folder for now)
- Files: `core/plugin_loader.py`, `plugins/` directory

**3.6 PowerShell & CMD Integration** *(HIGH — IT workhorse)*
- Direct PowerShell script execution as an action type
- Output capture and parsing
- Run as admin option
- Script templates library
- Files: `core/powershell.py`, `scripts/powershell/` templates

### ⚡ PERFORMANCE & RELIABILITY

**3.7 Multi-Agent Sessions** *(MEDIUM — parallel work)*
- Run multiple goals simultaneously on different virtual desktops
- Agent pool with queue system
- Priority levels: urgent (interrupt), normal, background
- Files: `core/agent_pool.py`, `core/virtual_desktop.py` enhancements

**3.8 Smart Recovery** *(MEDIUM — self-healing)*
- Auto-retry failed actions with different tier
- Detect and dismiss popup dialogs ("Are you sure?", "Update available")
- Window state recovery (re-open closed windows)
- Process watchdog (restart crashed apps mid-run)
- Files: `core/recovery.py`, `core/popup_handler.py`

### 🎨 UI/UX POLISH

**3.9 Professional GUI Overhaul**
- Split-pane: script editor (left) + live view (right)
- Tabbed interface: Dashboard | Scripts | Workflows | History | Settings
- Drag-and-drop script builder
- Markdown render for chat/notes
- System tray: quick actions menu, status indicator, notification balloons
- Toast notifications for long-running tasks
- Dark/light with the sentinel theme as default
- Files: rewrite `gui/app.py` with tabbed layout

**3.10 Notification System** *(LOW — awareness)*
- Desktop toast on task completion
- Email notification (configurable)
- Webhook callback (POST to URL when done)
- Slack/Discord webhook support
- Files: `core/notifications.py`

### 🚀 DEPLOYMENT

**3.11 One-Click Installer** *(HIGH — shareable)*
- PyInstaller → single .exe with embedded Python
- Inno Setup wizard: install, configure provider, go
- Auto-start as system tray app on login
- Silent install mode for IT deployment
- Files: `installer/setup.iss`, `build.py`

**3.12 Portable Mode** *(MEDIUM — USB stick)*
- Run from USB without installation
- Config in app directory instead of AppData
- Self-contained Python runtime
- Files: `portable/` directory, `main.py` auto-detect

### 🔒 SECURITY (Work-Ready)

**3.13 Enterprise Security** *(HIGH — IT compliance)*
- API key encryption at rest (Windows DPAPI)
- Role-based access: Viewer (watch only), Operator (run scripts), Admin (configure)
- Audit log export: PDF report with timestamps, screenshots, actions
- Sensitive field masking in logs (already partial)
- Session timeout for API
- Files: `core/auth.py`, `core/encryption.py`, `api/auth_middleware.py`

## Priority Order

| Phase | Features | Timeline |
|-------|----------|----------|
| **Phase 1** | Script Recorder, IT Quick Actions, PowerShell integration | Week 1-2 |
| **Phase 2** | Workflow Builder, Web Dashboard | Week 3-4 |
| **Phase 3** | Plugin System, Multi-Agent, Smart Recovery | Week 5-6 |
| **Phase 4** | One-Click Installer, Enterprise Security, Polish | Week 7-8 |

## Architecture Changes

```
sentinel-desktop/
├── main.py                 # Entry (unchanged)
├── core/
│   ├── engine.py           # Agent loop (enhanced for multi-agent)
│   ├── action_executor.py  # 37+ actions (add powershell, script_run)
│   ├── recorder.py         # NEW — action capture → JSON script
│   ├── script_engine.py    # NEW — replay recorded scripts
│   ├── workflow.py         # NEW — multi-step workflow engine
│   ├── scheduler.py        # NEW — cron-like scheduling
│   ├── powershell.py       # NEW — PS script execution
│   ├── agent_pool.py       # NEW — multi-agent manager
│   ├── recovery.py         # NEW — self-healing actions
│   ├── popup_handler.py    # NEW — dismiss unwanted dialogs
│   ├── notifications.py    # NEW — toast/email/webhook
│   ├── auth.py             # NEW — RBAC roles
│   ├── encryption.py       # NEW — DPAPI key storage
│   └── ... (existing modules)
├── api/
│   ├── server.py           # Enhanced with auth middleware
│   ├── auth_middleware.py  # NEW — JWT/session auth
│   └── static.py           # NEW — serve web dashboard
├── gui/
│   ├── app.py              # Rewritten: tabbed layout
│   ├── tabs/
│   │   ├── dashboard.py    # NEW — main overview tab
│   │   ├── scripts.py      # NEW — script library + editor
│   │   ├── workflows.py    # NEW — workflow builder
│   │   ├── history.py      # NEW — run history with replay
│   │   └── settings.py     # NEW — settings tab (extracted)
│   └── ... (existing)
├── web/                    # NEW — React dashboard
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   └── pages/
│   ├── package.json
│   └── vite.config.js
├── scripts/                # NEW — script library
│   ├── it_support/         # Pre-built IT scripts
│   │   ├── password_reset.json
│   │   ├── disk_cleanup.json
│   │   ├── network_diag.json
│   │   └── ...
│   ├── powershell/         # PS templates
│   │   ├── get_event_errors.ps1
│   │   ├── list_installed_software.ps1
│   │   └── ...
│   └── examples/           # Demo scripts
├── plugins/                # NEW — extensible plugins
│   ├── ad_manager.py       # Active Directory plugin
│   ├── ssh_tunnel.py       # SSH tunnel manager
│   └── template.py         # Plugin template/docs
└── installer/              # NEW — packaging
    ├── setup.iss           # Inno Setup script
    └── build.py            # PyInstaller build script
```

## Success Metrics

- [ ] Brandon uses it daily at Premier Networx for IT support tasks
- [ ] Can record a 10-step task in < 30 seconds
- [ ] Can replay any recorded task with one click
- [ ] Web dashboard accessible from phone/tablet
- [ ] Coworker can install and start using in < 5 minutes
- [ ] Password reset takes < 30 seconds from system tray
- [ ] Overnight batch runs complete unattended
- [ ] Audit log generates a manager-friendly PDF report
