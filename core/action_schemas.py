"""Pydantic validation for parsed LLM actions.

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
# Registry
# ---------------------------------------------------------------------------

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
