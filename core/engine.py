"""
Sentinel Desktop v2 — Agent Engine.

The main agent loop: user provides a goal, the engine takes screenshots,
sends them to the LLM, receives action decisions, executes them, and
repeats until completion or step budget exhaustion.

Supports both sync and async usage:
  - sync: engine.run(goal)           — blocks until done, used by GUI/API
  - async: await engine.run_goal(goal) — for future async callers
"""

import json
import logging
import re
import time
import asyncio
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from core.llm_client import LLMClient
from core.action_executor import ActionExecutor
from core.screenshot import capture_to_base64, capture_screen
from core import system_info as sysinfo
from core import window_manager as wm
from core.provider_registry import get_base_url

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are Sentinel Desktop Agent v2 — an AI assistant that controls a Windows \
desktop to accomplish the user's goal. You can see the screen, move the mouse, \
type, and interact with applications.

## Environment
{env_context}

## Available Actions
Return a single JSON object with an "action" field and relevant parameters:

| Action | Parameters | Description |
|--------|-----------|-------------|
| click | x, y, button? | Click at screen coordinates |
| click_image | template_path, confidence? | Find and click a template image |
| type_text | text | Type text character by character |
| press_key | key | Press a single key (enter, tab, escape, etc.) |
| hotkey | keys (list) | Press key combo, e.g. ["ctrl","c"] |
| scroll | amount | Scroll (positive=up, negative=down) |
| screenshot | (none) | Take a fresh screenshot |
| find_image | template_path, confidence? | Find image on screen, return position |
| wait_for_image | template_path, timeout? | Wait for image to appear |
| wait | seconds | Wait N seconds |
| open_app | path, args? | Start a program |
| focus_window | title | Bring window to front by title |
| close_window | title | Close a window by title |
| list_windows | (none) | List all visible windows |
| read_file | path | Read a text file |
| write_file | path, content | Write a text file |
| list_directory | path? | List directory contents |
| clipboard_read | (none) | Read clipboard text |
| clipboard_write | text | Write to clipboard |
| system_info | (none) | Get system details |
| list_processes | (none) | List running processes |
| kill_process | pid or name | Kill a process |
| note | text | Make a note (no side effects) |
| finish | summary | Signal task completion |

## Safety Rules (MSP)
1. **Sensitive fields**: Never type into password/credential fields without explicit instruction.
2. **Tenant lockdown**: In tenant mode, restrict file access to tenant-scoped paths.
3. **Destructive actions**: Always confirm before killing processes, closing windows, or deleting files.
4. **Honesty**: If you cannot see something clearly, say so. Tag unverified claims as [UNVERIFIED].

## Guidelines
- Look at the screenshot carefully before acting.
- Break complex goals into small, atomic steps.
- After each action, observe the result before proceeding.
- If something goes wrong, note it and try an alternative approach.
- When finished, call finish with a summary of what was accomplished.
- Be efficient — don't take unnecessary screenshots or repeat actions.

IMPORTANT: Reply with ONLY a JSON object. No markdown, no explanation, just the JSON.
Example: {"action": "click", "x": 500, "y": 300}
"""


class AgentEngine:
    """The main agent loop that drives desktop automation via LLM."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.llm = LLMClient()
        self.executor = ActionExecutor()

        # Public state (accessed by GUI and API)
        self.running = False
        self.step = 0
        self.max_steps = self.config.get("max_steps", 100)
        self.notes: List[str] = []
        self.forensic_log: List[Dict] = []
        self.on_step_callback: Optional[Callable] = None
        self.finish_summary: str = ""

    # ── Sync entry point ────────────────────────────────────────────────

    def run(self, goal: str) -> Dict[str, Any]:
        """Execute agent loop synchronously. Blocks until done."""
        self.running = True
        self.step = 0
        self.notes = []
        self.forensic_log = []
        self.finish_summary = ""

        provider = self.config.get("provider", "")
        api_key = self.config.get("api_key", "")
        model = self.config.get("model", "")

        if not api_key and provider not in ("ollama", "lmstudio", "custom"):
            return {"steps": 0, "notes": ["Error: API key not configured"]}
        if not model:
            return {"steps": 0, "notes": ["Error: Model not configured"]}

        # Build system prompt
        env_context = self._build_env_context()
        system_prompt = SYSTEM_PROMPT.format(env_context=env_context)
        messages = [{"role": "system", "content": system_prompt}]

        # Initial screenshot + goal
        screenshot_b64 = capture_to_base64()
        self._add_vision_message(messages, screenshot_b64,
                                 f"Goal: {goal}\n\nI can see this screen. What should I do first?")

        start_time = time.time()

        try:
            while self.running and self.step < self.max_steps:
                self.step += 1
                logger.info("Step %d/%d", self.step, self.max_steps)

                # Call LLM
                try:
                    response_text = self.llm.chat(
                        provider=provider,
                        api_key=api_key,
                        model=model,
                        messages=messages,
                        temperature=0.1,
                    )
                except Exception as exc:
                    logger.error("LLM call failed: %s", exc)
                    self.notes.append(f"LLM error at step {self.step}: {exc}")
                    break

                # Add to conversation
                messages.append({"role": "assistant", "content": response_text})

                # Parse action from response
                action = self._parse_action(response_text)
                if not action:
                    # LLM didn't return valid JSON, try to continue
                    self.notes.append(f"Step {self.step}: No valid action parsed from LLM response")
                    messages.append({
                        "role": "user",
                        "content": "Please respond with a valid JSON action. Only JSON, no other text.",
                    })
                    continue

                action_name = action.get("action", "")

                # Check for finish
                if action_name == "finish":
                    self.finish_summary = action.get("summary", "Task completed")
                    self.notes.append(self.finish_summary)
                    self._log_step(action, {"ok": True, "msg": self.finish_summary})
                    self.running = False
                    break

                # Log the action
                self._log_step(action, {"pending": True})

                # Execute the action
                result = self.executor.execute_sync(action)
                log_result = {
                    "ok": result.get("success", True),
                    "msg": str(result.get("output", ""))[:500],
                }
                self._log_step_result(self.step, log_result)

                if action_name == "note":
                    self.notes.append(action.get("text", ""))

                # Notify callback
                if self.on_step_callback:
                    try:
                        self.on_step_callback(
                            step=self.step,
                            action=action,
                            result=log_result,
                            screenshot=screenshot_b64,
                        )
                    except Exception:
                        pass

                # Take new screenshot for next iteration
                if self.running and self.config.get("auto_screenshot", True):
                    screenshot_b64 = capture_to_base64()
                    self._add_vision_message(
                        messages, screenshot_b64,
                        f"Step {self.step} result: {log_result['msg'][:200]}. Current screen:",
                    )

        except Exception as exc:
            logger.exception("Agent run error")
            self.notes.append(f"Fatal error: {exc}")
        finally:
            self.running = False

        elapsed = time.time() - start_time
        logger.info("Agent run finished: steps=%d, elapsed=%.1fs", self.step, elapsed)

        return {
            "steps": self.step,
            "notes": self.notes,
            "log": self.forensic_log,
            "finish_summary": self.finish_summary,
            "elapsed_seconds": round(elapsed, 2),
        }

    def stop(self):
        """Stop the agent loop."""
        self.running = False
        logger.info("Agent stop requested")

    # ── Internal ────────────────────────────────────────────────────────

    def _build_env_context(self) -> str:
        info = sysinfo.brief_system_info() if hasattr(sysinfo, 'brief_system_info') else ""
        active_win = ""
        try:
            windows = wm.list_windows()
            for w in windows:
                if w.get("is_focused"):
                    active_win = f"\nActive Window: {w['title']}"
                    break
        except Exception:
            pass
        tenant = ""
        if self.config.get("tenant_name"):
            tenant = f"\nTenant: {self.config['tenant_name']}"
            if self.config.get("tenant_lockdown"):
                tenant += " (LOCKDOWN MODE)"
        return info + active_win + tenant

    def _add_vision_message(self, messages: list, screenshot_b64: str, text: str):
        """Add a vision message (screenshot + text) to the conversation."""
        provider = self.config.get("provider", "")
        if provider == "anthropic":
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image", "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": screenshot_b64,
                    }},
                ],
            })
        else:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{screenshot_b64}",
                    }},
                ],
            })

    def _parse_action(self, response: str) -> Optional[Dict]:
        """Extract JSON action from LLM response text."""
        # Try direct JSON parse
        text = response.strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "action" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                if isinstance(parsed, dict) and "action" in parsed:
                    return parsed
            except json.JSONDecodeError:
                pass

        # Try finding any JSON object in the response
        brace_match = re.search(r'\{[^{}]*"action"[^{}]*\}', text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _log_step(self, action: Dict, result: Dict):
        self.forensic_log.append({
            "step": self.step,
            "action": action.get("action"),
            "params": {k: v for k, v in action.items() if k != "action"},
            "result": result,
            "timestamp": datetime.now().isoformat(),
        })

    def _log_step_result(self, step: int, result: Dict):
        for entry in reversed(self.forensic_log):
            if entry.get("step") == step:
                entry["result"] = result
                break

    def export_log(self) -> str:
        return json.dumps(self.forensic_log, indent=2, ensure_ascii=False)
