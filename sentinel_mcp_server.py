#!/usr/bin/env python3
"""Sentinel MCP Server — Model Context Protocol wrapper for Sentinel Desktop API.

Proxies MCP tool calls to the Sentinel Desktop FastAPI server over HTTP.
Works with sentinel-desktop running locally or on a remote host (e.g. homeserver).

Environment variables (API proxy):
  SENTINEL_API_URL   — Base URL of the Sentinel Desktop API (default: http://localhost:8091)
  SENTINEL_API_TOKEN — Optional bearer token for API auth (default: none)

Environment variables (MCP transport):
  SENTINEL_MCP_TRANSPORT — 'stdio' (default) or 'http'/'sse' for Tailscale fleet sharing
  SENTINEL_MCP_HOST      — Bind host for HTTP transport (default: 100.86.200.42, NUKE tailnet IP)
  SENTINEL_MCP_PORT      — Bind port for HTTP transport (default: 9192)
  MCP_AUTH_TOKEN         — Static bearer token to protect the HTTP MCP endpoint (optional)

Entry points (after pip install sentinel-desktop):
  sentinel-mcp-server                              # stdio transport
  SENTINEL_MCP_TRANSPORT=http sentinel-mcp-server  # HTTP transport
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = os.environ.get("SENTINEL_API_URL", "http://localhost:8091").rstrip("/")
API_TOKEN = os.environ.get("SENTINEL_API_TOKEN", "")
HTTP_TIMEOUT = 30.0  # seconds

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _headers() -> dict[str, str]:
    """Build request headers, conditionally including auth."""
    h: dict[str, str] = {"Content-Type": "application/json"}
    if API_TOKEN:
        h["Authorization"] = f"Bearer {API_TOKEN}"
    return h


def _api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET a JSON endpoint, return parsed dict. Raises on HTTP errors."""
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        r = client.get(f"{API_BASE}{path}", headers=_headers(), params=params)
        r.raise_for_status()
        return r.json()


def _api_post(path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST JSON to an endpoint, return parsed dict. Raises on HTTP errors."""
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        r = client.post(f"{API_BASE}{path}", headers=_headers(), json=body or {})
        r.raise_for_status()
        return r.json()


def _api_put(path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """PUT JSON to an endpoint, return parsed dict. Raises on HTTP errors."""
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        r = client.put(f"{API_BASE}{path}", headers=_headers(), json=body or {})
        r.raise_for_status()
        return r.json()


def _api_delete(path: str) -> dict[str, Any]:
    """DELETE an endpoint, return parsed dict. Raises on HTTP errors."""
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        r = client.delete(f"{API_BASE}{path}", headers=_headers())
        r.raise_for_status()
        return r.json()


def _err(e: Exception) -> str:
    """Format an exception into a concise error string for MCP responses."""
    msg = str(e)
    if isinstance(e, httpx.HTTPStatusError):
        try:
            detail = e.response.json().get("detail", e.response.text[:200])
        except Exception:
            detail = e.response.text[:200]
        msg = f"HTTP {e.response.status_code}: {detail}"
    return msg


# ---------------------------------------------------------------------------
# MCP Server definition
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="sentinel",
    instructions=(
        "Sentinel Desktop MCP — remote control for the Sentinel Desktop automation agent. "
        "Use these tools to take screenshots, run desktop commands, manage agent goals, "
        "list windows/processes, run scripts/workflows, manage the fleet, and more. "
        "The sentinel-desktop API must be running for these tools to work."
    ),
)


# ── Agent Control ─────────────────────────────────────────────────────────


@mcp.tool()
def goal(text: str, max_steps: int | None = None, approval_mode: bool | None = None) -> str:
    """Start an autonomous agent run with a natural language goal.

    The agent will see the screen, move the mouse, click, type, and interact
    with desktop applications to accomplish the goal. Use 'stop' to cancel.
    """
    try:
        body: dict[str, Any] = {"goal": text}
        if max_steps is not None:
            body["max_steps"] = max_steps
        if approval_mode is not None:
            body["approval_mode"] = approval_mode
        return json.dumps(_api_post("/goal", body))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def command(action: str) -> str:
    """Execute a single desktop command via the Sentinel agent.

    Pass either a JSON action dict string (e.g. '{"action": "click", "x": 100, "y": 200}')
    or plain text (treated as a note/text action).
    """
    try:
        return json.dumps(_api_post("/command", {"command": action}))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def stop() -> str:
    """Stop the currently running agent."""
    try:
        return json.dumps(_api_post("/stop"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def status() -> str:
    """Get the current agent status — running state, step count, notes."""
    try:
        return json.dumps(_api_get("/status"))
    except Exception as e:
        return f"Error: {_err(e)}"


# ── Screen & System Info ──────────────────────────────────────────────────


@mcp.tool()
def screenshot() -> str:
    """Capture a screenshot of the desktop. Returns base64-encoded PNG.

    The image is the full desktop capture. Use this to see what's on screen
    before issuing click/type commands.
    """
    try:
        return json.dumps(_api_get("/screenshot"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def windows() -> str:
    """List all visible desktop windows with titles and positions."""
    try:
        return json.dumps(_api_get("/windows"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def processes() -> str:
    """List running processes (top 100 by CPU/memory)."""
    try:
        return json.dumps(_api_get("/processes"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def system_info() -> str:
    """Get system information — OS, CPU, memory, disk, network."""
    try:
        return json.dumps(_api_get("/system"))
    except Exception as e:
        return f"Error: {_err(e)}"


# ── Configuration ─────────────────────────────────────────────────────────


@mcp.tool()
def get_config() -> str:
    """Read the current Sentinel Desktop configuration."""
    try:
        return json.dumps(_api_get("/config"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def set_config(
    provider: str | None = None,
    model: str | None = None,
    max_steps: int | None = None,
    approval_mode: bool | None = None,
    theme: str | None = None,
) -> str:
    """Update Sentinel Desktop configuration at runtime.

    All parameters are optional — only provided fields are updated.
    """
    try:
        body: dict[str, Any] = {}
        if provider is not None:
            body["provider"] = provider
        if model is not None:
            body["model"] = model
        if max_steps is not None:
            body["max_steps"] = max_steps
        if approval_mode is not None:
            body["approval_mode"] = approval_mode
        if theme is not None:
            body["theme"] = theme
        return json.dumps(_api_put("/config", body))
    except Exception as e:
        return f"Error: {_err(e)}"


# ── Logging ───────────────────────────────────────────────────────────────


@mcp.tool()
def log() -> str:
    """Get the forensic run log — every action the agent has taken."""
    try:
        return json.dumps(_api_get("/log"))
    except Exception as e:
        return f"Error: {_err(e)}"


# ── Scripts ───────────────────────────────────────────────────────────────


@mcp.tool()
def list_scripts() -> str:
    """List all available automation scripts in the scripts/ directory."""
    try:
        return json.dumps(_api_get("/scripts"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def run_script(path: str, params: dict[str, Any] | None = None) -> str:
    """Execute a saved automation script by path.

    Args:
        path: Script filename or relative path (e.g. 'scripts/disk_cleanup.json')
        params: Optional parameters to pass to the script
    """
    try:
        return json.dumps(_api_post("/scripts/run", {"path": path, "params": params}))
    except Exception as e:
        return f"Error: {_err(e)}"


# ── PowerShell ────────────────────────────────────────────────────────────


@mcp.tool()
def powershell(command: str) -> str:
    """Run a PowerShell command on the Sentinel Desktop host.

    Returns stdout, stderr, exit code, and parsed objects.
    Only available when Sentinel Desktop runs on Windows.
    """
    try:
        return json.dumps(_api_post("/powershell", {"command": command}))
    except Exception as e:
        return f"Error: {_err(e)}"


# ── Workflows ─────────────────────────────────────────────────────────────


@mcp.tool()
def list_workflows() -> str:
    """List all saved automation workflows."""
    try:
        return json.dumps(_api_get("/workflows"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def run_workflow(path: str, variables: dict[str, Any] | None = None) -> str:
    """Execute a workflow by path with optional variables."""
    try:
        return json.dumps(_api_post("/workflows/run", {"path": path, "variables": variables}))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def list_workflow_templates() -> str:
    """List workflow builder templates."""
    try:
        return json.dumps(_api_get("/workflows/builder/templates"))
    except Exception as e:
        return f"Error: {_err(e)}"


# ── Scheduler ─────────────────────────────────────────────────────────────


@mcp.tool()
def list_scheduled_tasks() -> str:
    """List all scheduled tasks."""
    try:
        return json.dumps(_api_get("/schedule"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def add_scheduled_task(
    name: str, goal: str, cron: str | None = None, delay_seconds: float | None = None
) -> str:
    """Create a new scheduled task for the agent to run.

    Provide either a cron expression or a delay in seconds for one-shot execution.
    """
    try:
        body: dict[str, Any] = {"name": name, "goal": goal}
        if cron is not None:
            body["cron"] = cron
        if delay_seconds is not None:
            body["delay_seconds"] = delay_seconds
        return json.dumps(_api_post("/schedule/add", body))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def remove_scheduled_task(task_id: str) -> str:
    """Remove a scheduled task by its ID."""
    try:
        return json.dumps(_api_post("/schedule/remove", {"task_id": task_id}))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def run_scheduled_task(task_id: str) -> str:
    """Trigger a scheduled task to run immediately."""
    try:
        return json.dumps(_api_post("/schedule/run", {"task_id": task_id}))
    except Exception as e:
        return f"Error: {_err(e)}"


# ── Agent Pool ────────────────────────────────────────────────────────────


@mcp.tool()
def list_agents() -> str:
    """List all agent pool sessions."""
    try:
        return json.dumps(_api_get("/agents"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def submit_agent(goal: str, config: dict[str, Any] | None = None, priority: str = "normal") -> str:
    """Submit a goal to the agent pool for parallel execution.

    Priority: 'low', 'normal', 'high', 'critical'.
    """
    try:
        body: dict[str, Any] = {"goal": goal, "priority": priority}
        if config is not None:
            body["config"] = config
        return json.dumps(_api_post("/agents/submit", body))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def cancel_agent(session_id: str) -> str:
    """Cancel a running agent session."""
    try:
        return json.dumps(_api_post("/agents/cancel", {"session_id": session_id}))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def agent_status(session_id: str) -> str:
    """Get the status of a specific agent session."""
    try:
        return json.dumps(_api_get(f"/agents/{session_id}"))
    except Exception as e:
        return f"Error: {_err(e)}"


# ── Fleet Management (v10) ────────────────────────────────────────────────


@mcp.tool()
def daemon_status() -> str:
    """Get the Sentinel daemon service status."""
    try:
        return json.dumps(_api_get("/daemon/status"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def daemon_start() -> str:
    """Start the Sentinel daemon service."""
    try:
        return json.dumps(_api_post("/daemon/start"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def daemon_stop() -> str:
    """Stop the Sentinel daemon service."""
    try:
        return json.dumps(_api_post("/daemon/stop"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def fleet_nodes() -> str:
    """List all registered fleet nodes."""
    try:
        return json.dumps(_api_get("/fleet/nodes"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def fleet_register(
    node_id: str,
    hostname: str,
    ip_address: str,
    role: str = "agent",
    tags: list[str] | None = None,
) -> str:
    """Register a new fleet node."""
    try:
        body: dict[str, Any] = {
            "node_id": node_id,
            "hostname": hostname,
            "ip_address": ip_address,
            "role": role,
        }
        if tags is not None:
            body["tags"] = tags
        return json.dumps(_api_post("/fleet/register", body))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def fleet_unregister(node_id: str) -> str:
    """Unregister a fleet node."""
    try:
        return json.dumps(_api_post("/fleet/unregister", {"node_id": node_id}))
    except Exception as e:
        return f"Error: {_err(e)}"


# ── Job Queue (v10) ───────────────────────────────────────────────────────


@mcp.tool()
def list_jobs(status: str | None = None) -> str:
    """List jobs in the queue. Optionally filter by status."""
    try:
        params = {}
        if status is not None:
            params["status"] = status
        return json.dumps(_api_get("/jobs", params=params))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def submit_job(goal: str, priority: int = 0, node_id: str | None = None) -> str:
    """Submit a new job to the job queue."""
    try:
        body: dict[str, Any] = {"goal": goal, "priority": priority}
        if node_id is not None:
            body["node_id"] = node_id
        return json.dumps(_api_post("/jobs/submit", body))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def job_status(job_id: str) -> str:
    """Get the status of a specific job."""
    try:
        return json.dumps(_api_get(f"/jobs/{job_id}"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def cancel_job(job_id: str) -> str:
    """Cancel a queued or running job."""
    try:
        return json.dumps(_api_post(f"/jobs/{job_id}/cancel"))
    except Exception as e:
        return f"Error: {_err(e)}"


# ── Recorder ──────────────────────────────────────────────────────────────


@mcp.tool()
def recorder_start() -> str:
    """Start recording desktop actions."""
    try:
        return json.dumps(_api_post("/recorder/start"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def recorder_stop(name: str = "Untitled", description: str = "") -> str:
    """Stop recording and save the captured actions as a script."""
    try:
        return json.dumps(_api_post("/recorder/stop", {"name": name, "description": description}))
    except Exception as e:
        return f"Error: {_err(e)}"


# ── Notifications ─────────────────────────────────────────────────────────


@mcp.tool()
def notify(title: str = "Sentinel", message: str = "", level: str = "info") -> str:
    """Send a desktop notification on the Sentinel host."""
    try:
        return json.dumps(
            _api_post("/notify", {"title": title, "message": message, "level": level})
        )
    except Exception as e:
        return f"Error: {_err(e)}"


# ── Plugins ───────────────────────────────────────────────────────────────


@mcp.tool()
def list_plugins() -> str:
    """List loaded Sentinel plugins."""
    try:
        return json.dumps(_api_get("/plugins"))
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def reload_plugin(name: str) -> str:
    """Reload a plugin by name."""
    try:
        return json.dumps(_api_post("/plugins/reload", {"name": name}))
    except Exception as e:
        return f"Error: {_err(e)}"


# ── Health Check ──────────────────────────────────────────────────────────


@mcp.tool()
def health() -> str:
    """Check if the Sentinel Desktop API is reachable and healthy."""
    try:
        r = _api_get("/status")
        return json.dumps(
            {"healthy": True, "api_url": API_BASE, "agent_running": r.get("running", False)}
        )
    except Exception as e:
        return json.dumps({"healthy": False, "api_url": API_BASE, "error": _err(e)})


# ── Agent Zero (Sentinel-EDGE / hackbox) ─────────────────────────────────

AGENT_ZERO_URL = os.environ.get("AGENT_ZERO_URL", "http://100.115.63.94:8080").rstrip("/")


@mcp.tool()
def agent_zero_run(prompt: str) -> str:
    """Send a task to Agent Zero on SENTINEL-EDGE (hackbox) for autonomous execution.

    Agent Zero is a self-prompting autonomous agent that can execute tasks on the
    hackbox (Linux/Nobara). It plans, acts, and iterates until the task is done.
    Use for tasks that need to run on the edge node, e.g. OS operations, file
    management, running scripts, or interacting with tools installed on hackbox.
    """
    try:
        with httpx.Client(timeout=300.0) as client:
            r = client.post(
                f"{AGENT_ZERO_URL}/run",
                headers=_headers(),
                json={"prompt": prompt},
            )
            r.raise_for_status()
            return r.text
    except Exception as e:
        return f"Error: {_err(e)}"


@mcp.tool()
def agent_zero_health() -> str:
    """Check if Agent Zero on hackbox is reachable."""
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{AGENT_ZERO_URL}/", headers=_headers())
            return json.dumps(
                {"reachable": r.status_code < 500, "status": r.status_code, "url": AGENT_ZERO_URL}
            )
    except Exception as e:
        return json.dumps({"reachable": False, "url": AGENT_ZERO_URL, "error": _err(e)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the MCP server.

    Transport is selected via SENTINEL_MCP_TRANSPORT env var (default: stdio).
    Set to 'http' (or 'streamable-http'/'sse') to listen over HTTP for Tailscale
    fleet sharing; SENTINEL_MCP_HOST, SENTINEL_MCP_PORT, and MCP_AUTH_TOKEN
    control the bind address and optional bearer-token auth.
    """
    transport = os.environ.get("SENTINEL_MCP_TRANSPORT", "stdio").lower()
    if transport in ("http", "streamable-http", "sse"):
        host = os.environ.get("SENTINEL_MCP_HOST", "100.86.200.42")  # NUKE tailnet IP
        port = int(os.environ.get("SENTINEL_MCP_PORT", "9192"))
        token = os.environ.get("MCP_AUTH_TOKEN")
        if token:
            from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

            mcp.auth = StaticTokenVerifier(tokens={token: {"client_id": "fleet", "scopes": []}})
        mcp.run(transport="http", host=host, port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
