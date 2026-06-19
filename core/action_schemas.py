"""Sentinel Desktop v3.0 — Pydantic validation for parsed LLM actions.

The agent loop in :mod:`core.engine` calls :func:`validate_action` immediately
after :meth:`AgentEngine._parse_action` succeeds. The function tries to
match the payload against a per-action :class:`pydantic.BaseModel` and
returns the (possibly coerced) payload plus a list of validation errors.

The engine does NOT abort on validation failure today — it logs the
errors via the forensic stream so we get signal before tightening the
gate. Once the LLM is consistently emitting valid actions, the caller
can change behaviour to reject invalid actions outright.

Actions not present in :data:`ACTION_MODELS` pass through unchanged.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# Reusable field annotations
_PixelCoord = Annotated[int, Field(ge=0, le=20000)]
_NonEmptyStr = Annotated[str, Field(min_length=1)]


class _ActionBase(BaseModel):
    """Common config — ignore unknown fields so the LLM can pass extras."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)


# ---------------------------------------------------------------------------
# Modeled actions
# ---------------------------------------------------------------------------


class ClickAction(_ActionBase):
    """Mouse click action — single, double, or right-click at screen coordinates.

    The ``action`` field determines the type: ``click``, ``double_click``,
    or ``right_click``.  A model validator auto-sets ``button``/``clicks``
    so the LLM doesn't have to be explicit about both.
    """

    action: Literal["click", "double_click", "right_click"]
    x: _PixelCoord
    y: _PixelCoord
    button: Literal["left", "right", "middle"] = "left"
    clicks: int = 1

    @model_validator(mode="after")
    def _derive_button_and_clicks(self) -> ClickAction:
        """Auto-set clicks=2 for double_click and button='right' for right_click."""
        if self.action == "double_click":
            self.clicks = 2
        if self.action == "right_click":
            self.button = "right"
        return self


class TypeTextAction(_ActionBase):
    """Type a text string at the current cursor position."""

    action: Literal["type_text"]
    text: str


class PressKeyAction(_ActionBase):
    """Press a single keyboard key (e.g. 'enter', 'tab', 'escape')."""

    action: Literal["press_key"]
    key: _NonEmptyStr


class HotkeyAction(_ActionBase):
    """Press a keyboard shortcut (e.g. ['ctrl', 'c'] for copy).

    Accepts 1–8 key names in the ``keys`` list.
    """

    action: Literal["hotkey"]
    keys: list[_NonEmptyStr] = Field(min_length=1, max_length=8)


class ScrollAction(_ActionBase):
    """Scroll the mouse wheel. Positive = up, negative = down."""

    action: Literal["scroll"]
    amount: Annotated[int, Field(ge=-50, le=50)]


class WaitAction(_ActionBase):
    """Caps the wait at 60s so an LLM can't stall the agent for hours."""

    action: Literal["wait"]
    seconds: Annotated[float, Field(ge=0.0, le=60.0)] = 1.0


class WriteFileAction(_ActionBase):
    """Write content to a file on disk. Creates the file if it doesn't exist."""

    action: Literal["write_file"]
    path: _NonEmptyStr
    content: str = ""


class ReadFileAction(_ActionBase):
    """Read the contents of a file from disk."""

    action: Literal["read_file"]
    path: _NonEmptyStr


class KillProcessAction(_ActionBase):
    """Terminate a running process by PID or name (at least one required)."""

    action: Literal["kill_process"]
    pid: Annotated[int, Field(ge=1)] | None = None
    name: str | None = None


# ---------------------------------------------------------------------------
# Web / Browser actions (v8.0 — Playwright)
# ---------------------------------------------------------------------------

_UrlStr = Annotated[str, Field(min_length=1, max_length=2048)]


class WebOpenAction(_ActionBase):
    """Navigate to a URL in the managed browser."""

    action: Literal["web_open"]
    url: _UrlStr
    wait_until: Literal["load", "domcontentloaded", "networkidle", "commit"] = "load"


class WebClickAction(_ActionBase):
    """Click an element in the browser by selector, text, or ARIA role."""

    action: Literal["web_click"]
    selector: str | None = None
    text: str | None = None
    role: str | None = None
    name: str | None = None
    button: Literal["left", "right", "middle"] = "left"
    click_count: Annotated[int, Field(ge=1, le=3)] = 1


class WebTypeAction(_ActionBase):
    """Type text into a browser form field."""

    action: Literal["web_type"]
    text: str
    selector: str | None = None
    label: str | None = None
    role: str | None = None
    name: str | None = None
    clear: bool = True


class WebReadAction(_ActionBase):
    """Read text content from the browser page or element."""

    action: Literal["web_read"]
    selector: str | None = None
    full_page: bool = False


class WebExtractAction(_ActionBase):
    """Extract structured data (tables, lists) from the browser page."""

    action: Literal["web_extract"]
    selector: str = "table"
    format: Literal["json", "text"] = "json"


class WebWaitForAction(_ActionBase):
    """Wait for an element or condition in the browser."""

    action: Literal["web_wait_for"]
    selector: str | None = None
    text: str | None = None
    state: Literal["visible", "hidden", "attached", "detached"] = "visible"
    timeout: Annotated[float, Field(ge=0.1, le=120.0)] = 30.0


class WebScreenshotAction(_ActionBase):
    """Capture a screenshot of the browser viewport or element."""

    action: Literal["web_screenshot"]
    selector: str | None = None
    full_page: bool = False


class WebEvalJsAction(_ActionBase):
    """Execute JavaScript in the browser context."""

    action: Literal["web_eval_js"]
    expression: _NonEmptyStr


class WebDownloadAction(_ActionBase):
    """Download a file from the browser."""

    action: Literal["web_download"]
    url: str | None = None
    save_path: str | None = None


class WebUploadAction(_ActionBase):
    """Upload files to a web form."""

    action: Literal["web_upload"]
    selector: _NonEmptyStr
    file_paths: list[_NonEmptyStr] = Field(min_length=1)


class WebTabsAction(_ActionBase):
    """Manage browser tabs — list, switch, new, close."""

    action: Literal["web_tabs"]
    tab_action: Literal["list", "switch", "new", "close"] = "list"
    index: Annotated[int, Field(ge=0)] | None = None
    url: str | None = None


# ---------------------------------------------------------------------------
# Netops / SSH actions (v9.0 — network device control)
# ---------------------------------------------------------------------------


class SSHConnectAction(_ActionBase):
    """Connect to a network device via SSH."""

    action: Literal["ssh_connect"]
    hostname: _NonEmptyStr
    username: str = ""
    password: str = ""
    port: Annotated[int, Field(ge=1, le=65535)] = 22
    key_filename: str | None = None


class SSHDisconnectAction(_ActionBase):
    """Disconnect from an SSH device."""

    action: Literal["ssh_disconnect"]
    hostname: _NonEmptyStr


class SSHRunAction(_ActionBase):
    """Run a command on a connected SSH device."""

    action: Literal["ssh_run"]
    hostname: _NonEmptyStr
    command: _NonEmptyStr
    timeout: Annotated[float, Field(ge=1.0, le=300.0)] = 30.0


class SSHShowAction(_ActionBase):
    """Run a device-aware show command via SSH."""

    action: Literal["ssh_show"]
    hostname: _NonEmptyStr
    what: Literal["version", "interfaces", "routing", "arp", "cpu", "logging", "config"]
    device_type: str = "generic"


class SSHPingAction(_ActionBase):
    """Ping a target from an SSH device."""

    action: Literal["ssh_ping"]
    hostname: _NonEmptyStr
    target: _NonEmptyStr
    count: Annotated[int, Field(ge=1, le=100)] = 4
    device_type: str = "generic"


class SSHTracerouteAction(_ActionBase):
    """Traceroute to a target from an SSH device."""

    action: Literal["ssh_traceroute"]
    hostname: _NonEmptyStr
    target: _NonEmptyStr
    device_type: str = "generic"


# ---------------------------------------------------------------------------
# Memory actions (v11.0 — persistent memory)
# ---------------------------------------------------------------------------


class MemoryStoreAction(_ActionBase):
    """Store a fact in semantic memory."""

    action: Literal["memory_store"]
    key: _NonEmptyStr
    value: _NonEmptyStr
    category: str = ""
    tags: list[str] | None = None


class MemoryRecallAction(_ActionBase):
    """Recall a fact from semantic memory by key."""

    action: Literal["memory_recall"]
    key: _NonEmptyStr


class MemorySearchAction(_ActionBase):
    """Search semantic memory by keyword."""

    action: Literal["memory_search"]
    query: _NonEmptyStr
    limit: Annotated[int, Field(ge=1, le=100)] = 10


class MemoryForgetAction(_ActionBase):
    """Delete a fact from semantic memory."""

    action: Literal["memory_forget"]
    key: _NonEmptyStr


# ---------------------------------------------------------------------------
# Conductor actions (v12.0 — multi-agent orchestration)
# ---------------------------------------------------------------------------


class ConductorRunAction(_ActionBase):
    """Decompose a complex goal into subtasks and execute in parallel."""

    action: Literal["conductor_run"]
    goal: _NonEmptyStr
    timeout: Annotated[float, Field(ge=10.0, le=600.0)] = 120.0


# ---------------------------------------------------------------------------
# Neuralis Brain actions (v18.0 — fleet-wide shared memory)
# ---------------------------------------------------------------------------


class BrainThinkAction(_ActionBase):
    """Persist a thought to the Neuralis Brain (shared fleet memory)."""

    action: Literal["brain_think"]
    content: _NonEmptyStr
    region: Literal["knowledge", "context", "preference", "decision"] = "knowledge"


class BrainRecallAction(_ActionBase):
    """Retrieve the most relevant thoughts from the fleet brain for a context string."""

    action: Literal["brain_recall"]
    context: _NonEmptyStr


class BrainSearchAction(_ActionBase):
    """Free-text search across all neurons in the fleet brain."""

    action: Literal["brain_search"]
    q: _NonEmptyStr


class BrainStatsAction(_ActionBase):
    """Return fleet brain health stats — neuron/synapse counts, active regions."""

    action: Literal["brain_stats"]


class BrainFireAction(_ActionBase):
    """Fire (reinforce) a specific neuron by ID — strengthens its connections."""

    action: Literal["brain_fire"]
    neuron_id: Annotated[int, Field(ge=1)]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# File Operations Plus (v13.0 — extended file management)
# ---------------------------------------------------------------------------


class DeleteFileAction(_ActionBase):
    """Delete a file or empty directory."""

    action: Literal["delete_file"]
    path: _NonEmptyStr
    force: bool = False


class MoveFileAction(_ActionBase):
    """Move or rename a file or directory."""

    action: Literal["move_file"]
    src: _NonEmptyStr
    dst: _NonEmptyStr


class CopyFileAction(_ActionBase):
    """Copy a file to a new location."""

    action: Literal["copy_file"]
    src: _NonEmptyStr
    dst: _NonEmptyStr


class MkdirAction(_ActionBase):
    """Create a directory."""

    action: Literal["mkdir"]
    path: _NonEmptyStr
    parents: bool = True


class StatFileAction(_ActionBase):
    """Get file metadata (size, modified, permissions)."""

    action: Literal["stat_file"]
    path: _NonEmptyStr


class FindFilesAction(_ActionBase):
    """Search for files matching a glob pattern."""

    action: Literal["find_files"]
    pattern: _NonEmptyStr
    root: str = "."
    max_results: Annotated[int, Field(ge=1, le=1000)] = 100


class ArchiveCreateAction(_ActionBase):
    """Create a zip archive from a list of files."""

    action: Literal["archive_create"]
    archive_path: _NonEmptyStr
    files: list[_NonEmptyStr] = Field(min_length=1)
    base_dir: str = "."


class ArchiveExtractAction(_ActionBase):
    """Extract a zip archive to a directory."""

    action: Literal["archive_extract"]
    archive_path: _NonEmptyStr
    dest_dir: str = "."


# ---------------------------------------------------------------------------
# Process & Service Control (v13.0 — OS integration)
# ---------------------------------------------------------------------------


class SetPriorityAction(_ActionBase):
    """Change process priority."""

    action: Literal["set_priority"]
    pid: Annotated[int, Field(ge=1)]
    priority: Literal["idle", "low", "normal", "high", "realtime"]


class GetEnvAction(_ActionBase):
    """Read an environment variable."""

    action: Literal["get_env"]
    name: _NonEmptyStr


class SetEnvAction(_ActionBase):
    """Set an environment variable."""

    action: Literal["set_env"]
    name: _NonEmptyStr
    value: str
    permanent: bool = False


class ServiceControlAction(_ActionBase):
    """Control a Windows service (start/stop/restart/query)."""

    action: Literal["service_control"]
    name: _NonEmptyStr
    control_action: Literal["start", "stop", "restart", "query"]


# ---------------------------------------------------------------------------
# Credential Vault (v13.0 — OS credential store)
# ---------------------------------------------------------------------------


class CredStoreAction(_ActionBase):
    """Store a credential in the OS credential vault."""

    action: Literal["cred_store"]
    key: _NonEmptyStr
    value: _NonEmptyStr


class CredReadAction(_ActionBase):
    """Read a credential from the OS credential vault."""

    action: Literal["cred_read"]
    key: _NonEmptyStr


# ---------------------------------------------------------------------------
# Registry (v13.0 — Windows registry operations)
# ---------------------------------------------------------------------------


class RegistryReadAction(_ActionBase):
    """Read a Windows registry value."""

    action: Literal["registry_read"]
    path: _NonEmptyStr
    value_name: str = ""


class RegistryWriteAction(_ActionBase):
    """Write a Windows registry value."""

    action: Literal["registry_write"]
    path: _NonEmptyStr
    value_name: _NonEmptyStr
    data: str
    reg_type: str = "REG_SZ"


class RegistryDeleteAction(_ActionBase):
    """Delete a Windows registry key or value."""

    action: Literal["registry_delete"]
    path: _NonEmptyStr
    value_name: str | None = None


ACTION_MODELS: dict[str, type[_ActionBase]] = {
    "click": ClickAction,
    "double_click": ClickAction,
    "right_click": ClickAction,
    "type_text": TypeTextAction,
    "press_key": PressKeyAction,
    "hotkey": HotkeyAction,
    "scroll": ScrollAction,
    "wait": WaitAction,
    "write_file": WriteFileAction,
    "read_file": ReadFileAction,
    "kill_process": KillProcessAction,
    # Web / Browser (v8.0)
    "web_open": WebOpenAction,
    "web_click": WebClickAction,
    "web_type": WebTypeAction,
    "web_read": WebReadAction,
    "web_extract": WebExtractAction,
    "web_wait_for": WebWaitForAction,
    "web_screenshot": WebScreenshotAction,
    "web_eval_js": WebEvalJsAction,
    "web_download": WebDownloadAction,
    "web_upload": WebUploadAction,
    "web_tabs": WebTabsAction,
    # Netops (v9.0)
    "ssh_connect": SSHConnectAction,
    "ssh_disconnect": SSHDisconnectAction,
    "ssh_run": SSHRunAction,
    "ssh_show": SSHShowAction,
    "ssh_ping": SSHPingAction,
    "ssh_traceroute": SSHTracerouteAction,
    # Memory (v11.0)
    "memory_store": MemoryStoreAction,
    "memory_recall": MemoryRecallAction,
    "memory_search": MemorySearchAction,
    "memory_forget": MemoryForgetAction,
    # Conductor (v12.0)
    "conductor_run": ConductorRunAction,
    # File Operations Plus (v13.0)
    "delete_file": DeleteFileAction,
    "move_file": MoveFileAction,
    "copy_file": CopyFileAction,
    "mkdir": MkdirAction,
    "stat_file": StatFileAction,
    "find_files": FindFilesAction,
    "archive_create": ArchiveCreateAction,
    "archive_extract": ArchiveExtractAction,
    # Process & Service Control (v13.0)
    "set_priority": SetPriorityAction,
    "get_env": GetEnvAction,
    "set_env": SetEnvAction,
    "service_control": ServiceControlAction,
    # Credential Vault (v13.0)
    "cred_store": CredStoreAction,
    "cred_read": CredReadAction,
    # Registry (v13.0)
    "registry_read": RegistryReadAction,
    "registry_write": RegistryWriteAction,
    "registry_delete": RegistryDeleteAction,
    # Neuralis Brain (v18.0)
    "brain_think": BrainThinkAction,
    "brain_recall": BrainRecallAction,
    "brain_search": BrainSearchAction,
    "brain_stats": BrainStatsAction,
    "brain_fire": BrainFireAction,
}


def validate_action(payload: Any) -> tuple[dict[str, Any], list[str]]:
    """Validate *payload* against the matching action model.

    Returns ``(sanitised_payload, errors)``:

    - ``sanitised_payload`` is the original dict for unmodeled actions
      or the pydantic-dumped dict (with defaults filled in) for modeled
      ones. Always safe for the executor to dispatch.
    - ``errors`` is a list of human-readable strings; empty when the
      payload is valid or when the action is not modeled.

    Never raises. Designed for warn-and-continue use in the engine loop.
    """
    if not isinstance(payload, dict):
        return {}, [f"action payload must be a dict, got {type(payload).__name__}"]

    name = payload.get("action")
    if not isinstance(name, str) or not name:
        return dict(payload), ["missing or non-string 'action' key"]

    model = ACTION_MODELS.get(name)
    if model is None:
        return dict(payload), []  # unmodeled — pass through

    try:
        instance = model.model_validate(payload)
    except ValidationError as exc:
        errors = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()]
        return dict(payload), errors

    return instance.model_dump(exclude_unset=False), []
