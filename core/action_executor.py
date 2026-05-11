"""
Sentinel Desktop v2 — Action executor.

Takes structured action dicts from the LLM and dispatches them to
the appropriate desktop, file, window, or process functions.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from core import desktop as desktop_mod
from core import window_manager as wm
from core import process_manager as pm
from core import file_ops
from core import clipboard as clip
from core import system_info as sysinfo
from core.screenshot import capture_screen, capture_to_base64, find_template, wait_for_template

logger = logging.getLogger(__name__)

# Sensitive field keywords — skip typing into these
SENSITIVE_FIELDS = [
    "password", "passwd", "secret", "token", "api_key",
    "credit_card", "ssn", "social_security", "pin",
]


class ActionExecutor:
    """Execute desktop actions returned by the LLM."""

    def __init__(self, approval_callback: Optional[Callable] = None):
        """
        Args:
            approval_callback: Async callable(action_dict) → bool.
                If provided, actions are sent for approval before execution.
        """
        self.approval_callback = approval_callback
        self._desktop = desktop_mod.DesktopEngine()
        self._log: List[Dict[str, Any]] = []

    @property
    def log(self) -> List[Dict[str, Any]]:
        return self._log

    async def execute(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single action.

        Args:
            action: Dict with at least 'action' key and relevant params.

        Returns:
            Result dict: {success, output, error}
        """
        action_type = action.get("action", "").lower()
        params = {k: v for k, v in action.items() if k != "action"}

        # Approval gate
        if self.approval_callback:
            approved = await self.approval_callback(action)
            if not approved:
                result = {"success": False, "output": "Action rejected by user", "error": "rejected"}
                self._log_entry(action_type, params, result)
                return result

        # Dispatch
        handler = self._dispatch_table.get(action_type)
        if handler:
            try:
                # Run sync functions in executor to not block the event loop
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(self, **params)
                else:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, lambda: handler(self, **params))
            except Exception as exc:
                logger.exception("Action '%s' failed", action_type)
                result = {"success": False, "output": str(exc), "error": type(exc).__name__}
        else:
            result = {"success": False, "output": f"Unknown action: {action_type}", "error": "unknown_action"}

        self._log_entry(action_type, params, result)
        return result

    def execute_sync(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous wrapper — executes action directly (no event loop needed)."""
        action_type = action.get("action", "").lower()
        params = {k: v for k, v in action.items() if k != "action"}

        handler = self._dispatch_table.get(action_type)
        if handler:
            try:
                result = handler(self, **params)
            except Exception as exc:
                logger.exception("Action '%s' failed", action_type)
                result = {"success": False, "output": str(exc), "error": type(exc).__name__}
        else:
            result = {"success": False, "output": f"Unknown action: {action_type}", "error": "unknown_action"}

        self._log_entry(action_type, params, result)
        return result

    def _log_entry(self, action_type: str, params: Dict, result: Dict) -> None:
        entry = {
            "action": action_type,
            "params": _sanitize_params(params),
            "success": result.get("success", False),
            "output_preview": str(result.get("output", ""))[:200],
        }
        self._log.append(entry)
        logger.info("Action: %-20s → %s", action_type, "OK" if result.get("success") else "FAIL")

    # -------------------------------------------------------------------
    # Action handlers (sync — wrapped by execute())
    # -------------------------------------------------------------------
    def _click(self, *, x: int, y: int, button: str = "left", **_) -> Dict:
        self._desktop.click(x, y, button=button)
        return {"success": True, "output": f"Clicked ({x}, {y})"}

    def _click_text(self, *, text: str, **_) -> Dict:
        # Text clicking relies on OCR which is not always available;
        # the LLM should use screenshot + coordinates instead.
        return {"success": False, "output": "click_text requires OCR — use click with coordinates from screenshot", "error": "not_implemented"}

    def _click_image(self, *, template_path: str, confidence: float = 0.8, **_) -> Dict:
        found = self._desktop.click_image(template_path, confidence)
        return {"success": found, "output": f"Template {'found and clicked' if found else 'not found'}"}

    def _type_text(self, *, text: str, **_) -> Dict:
        # Sensitive field check
        if _contains_sensitive(text):
            return {"success": False, "output": "Blocked: text appears to contain sensitive data", "error": "sensitive_field"}
        self._desktop.type_text(text)
        return {"success": True, "output": f"Typed {len(text)} characters"}

    def _press_key(self, *, key: str, **_) -> Dict:
        self._desktop.press_key(key)
        return {"success": True, "output": f"Pressed {key}"}

    def _hotkey(self, *, keys: list, **_) -> Dict:
        self._desktop.hotkey(*keys)
        return {"success": True, "output": f"Hotkey: {'+'.join(keys)}"}

    def _scroll(self, *, amount: int, **_) -> Dict:
        self._desktop.scroll(amount)
        return {"success": True, "output": f"Scrolled {amount}"}

    def _screenshot(self, **_) -> Dict:
        b64 = capture_to_base64()
        return {"success": True, "output": f"Screenshot captured ({len(b64)} chars base64)", "screenshot": b64}

    def _find_image(self, *, template_path: str, confidence: float = 0.8, **_) -> Dict:
        pos = find_template(template_path, confidence)
        if pos:
            return {"success": True, "output": f"Found at ({pos[0]}, {pos[1]})", "position": list(pos)}
        return {"success": False, "output": "Image not found on screen"}

    def _wait_for_image(self, *, template_path: str, timeout: int = 30, **_) -> Dict:
        pos = wait_for_template(template_path, float(timeout))
        if pos:
            return {"success": True, "output": f"Image appeared at ({pos[0]}, {pos[1]})", "position": list(pos)}
        return {"success": False, "output": f"Timed out after {timeout}s"}

    def _open_app(self, *, path: str, args: list = None, **_) -> Dict:
        pid = pm.start_process(path, args)
        if pid:
            return {"success": True, "output": f"Started process (pid {pid})"}
        return {"success": False, "output": "Failed to start process"}

    def _close_app(self, *, name: str = None, pid: int = None, **_) -> Dict:
        target = pid or name
        if target is None:
            return {"success": False, "output": "Provide 'name' or 'pid'"}
        killed = pm.kill_process(target)
        return {"success": killed, "output": f"Process {target} {'killed' if killed else 'not found'}"}

    def _focus_window(self, *, title: str, **_) -> Dict:
        ok = wm.focus_window(title)
        return {"success": ok, "output": f"Window '{title}' {'focused' if ok else 'not found'}"}

    def _list_windows(self, **_) -> Dict:
        windows = wm.list_windows()
        return {"success": True, "output": windows}

    def _read_file(self, *, path: str, **_) -> Dict:
        content = file_ops.read_file(path)
        if content is not None:
            preview = content[:5000]
            return {"success": True, "output": preview, "length": len(content)}
        return {"success": False, "output": "File not found or unreadable"}

    def _write_file(self, *, path: str, content: str, **_) -> Dict:
        ok = file_ops.write_file(path, content)
        return {"success": ok, "output": f"File {'written' if ok else 'write failed'}"}

    def _list_directory(self, *, path: str = ".", **_) -> Dict:
        entries = file_ops.list_directory(path)
        if entries is not None:
            return {"success": True, "output": entries}
        return {"success": False, "output": "Directory not found"}

    def _clipboard_read(self, **_) -> Dict:
        text = clip.clipboard_read()
        return {"success": text is not None, "output": text or ""}

    def _clipboard_write(self, *, text: str, **_) -> Dict:
        ok = clip.clipboard_write(text)
        return {"success": ok, "output": f"Clipboard {'updated' if ok else 'failed'}"}

    def _system_info(self, **_) -> Dict:
        info = sysinfo.system_info()
        return {"success": True, "output": info}

    def _list_processes(self, **_) -> Dict:
        procs = pm.list_processes()
        return {"success": True, "output": procs[:100]}  # Cap at 100

    def _start_process(self, *, path: str, args: list = None, **_) -> Dict:
        pid = pm.start_process(path, args)
        return {"success": pid is not None, "output": f"pid={pid}"}

    def _kill_process(self, *, pid: int = None, name: str = None, **_) -> Dict:
        target = pid or name
        killed = pm.kill_process(target)
        return {"success": killed, "output": f"Process {target} {'killed' if killed else 'not found'}"}

    def _note(self, *, text: str, **_) -> Dict:
        """Agent makes a note to itself — no-op for execution, logged."""
        logger.info("Agent note: %s", text)
        return {"success": True, "output": text}

    def _finish(self, *, summary: str = "", **_) -> Dict:
        """Signal that the agent is done."""
        return {"success": True, "output": summary, "done": True}

    # Dispatch table
    _dispatch_table: Dict[str, Callable] = {
        "click": _click,
        "click_text": _click_text,
        "click_image": _click_image,
        "type_text": _type_text,
        "press_key": _press_key,
        "hotkey": _hotkey,
        "scroll": _scroll,
        "screenshot": _screenshot,
        "find_image": _find_image,
        "wait_for_image": _wait_for_image,
        "open_app": _open_app,
        "close_app": _close_app,
        "focus_window": _focus_window,
        "list_windows": _list_windows,
        "read_file": _read_file,
        "write_file": _write_file,
        "list_directory": _list_directory,
        "clipboard_read": _clipboard_read,
        "clipboard_write": _clipboard_write,
        "system_info": _system_info,
        "list_processes": _list_processes,
        "start_process": _start_process,
        "kill_process": _kill_process,
        "note": _note,
        "finish": _finish,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _contains_sensitive(text: str) -> bool:
    """Check if text looks like it contains sensitive data.
    Used to prevent accidental typing of secrets."""
    # This is a lightweight check; the real protection is context-aware.
    lower = text.lower()
    for keyword in SENSITIVE_FIELDS:
        if keyword in lower and len(text) < 100:
            # Short text containing a sensitive keyword — likely a credential
            return True
    return False


def _sanitize_params(params: Dict) -> Dict:
    """Remove potentially large data from params for logging."""
    sanitized = {}
    for k, v in params.items():
        if isinstance(v, str) and len(v) > 200:
            sanitized[k] = v[:200] + "..."
        elif isinstance(v, (list, dict)) and len(str(v)) > 500:
            sanitized[k] = f"<{type(v).__name__} len={len(v)}>"
        else:
            sanitized[k] = v
    return sanitized
