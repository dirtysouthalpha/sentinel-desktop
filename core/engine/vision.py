"""Vision message building, screenshot capture, and context construction.

Handles the Anthropic-vs-OpenAI vision message formatting, screenshot
pruning to bound token usage, and building the initial system prompt with
environment and app context.

Implementation note: the ``sysinfo``, ``wm``, ``detect_profile``, and
``capture_to_base64`` names are accessed via deferred imports from
``core.engine`` so that tests can patch them at ``core.engine.*`` and have
the patches take effect inside these methods.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class VisionMessageBuilder:
    """Builds vision messages and context for the agent loop.

    Captures screenshots, formats vision messages (Anthropic vs OpenAI),
    prunes old screenshots, and builds the initial system prompt with
    environment and app context.

    Args:
        config: The engine config dict.
        step_ref: Callable that returns the current step number.
        image_history: Max number of screenshot messages to keep in-context.
    """

    def __init__(self, config: dict[str, Any], step_ref: callable, image_history: int) -> None:
        self._config = config
        self._step_ref = step_ref
        self._image_history = image_history

    def build_initial_messages(
        self,
        goal: str,
        env_context: str | None = None,
        app_context: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build system prompt and initial screenshot message list.

        Constructs the system prompt from the template with environment and
        app context injected, then captures an initial screenshot and adds
        the goal as the first user message.

        Args:
            goal: The user's goal string.
            env_context: Pre-computed environment context. If None, computed
                via ``build_env_context()``.
            app_context: Pre-computed app context. If None, computed via
                ``build_app_context()``.
        """
        from core.engine import SYSTEM_PROMPT, capture_to_base64

        if env_context is None:
            env_context = self.build_env_context()
        system_prompt = SYSTEM_PROMPT.replace("{env_context}", env_context)

        if app_context is None:
            app_context = self.build_app_context()
        system_prompt = system_prompt.replace("{app_context}", app_context)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

        # Initial screenshot + goal
        try:
            screenshot_b64 = capture_to_base64(monitor=self._config.get("monitor"))
        except (OSError, ValueError, RuntimeError) as exc:
            logger.warning("Initial screen capture failed: %s", exc)
            screenshot_b64 = ""
        self.add_vision_message(
            messages,
            screenshot_b64,
            f"Goal: {goal}\n\nI can see this screen. What should I do first?",
        )
        return messages

    def build_env_context(self) -> str:
        """Gather OS info, active window title, and tenant metadata for the prompt."""
        from core.engine import sysinfo, wm

        try:
            info = sysinfo.brief_system_info()
        except (OSError, RuntimeError) as exc:
            logger.debug("brief_system_info failed: %s", exc)
            info = ""
        active_win = ""
        try:
            windows = wm.list_windows()
            for w in windows:
                if w.get("is_focused"):
                    active_win = f"\nActive Window: {w['title']}"
                    break
        except (OSError, RuntimeError) as exc:
            logger.warning("Failed to detect active window: %s", exc)
        tenant = ""
        if self._config.get("tenant_name"):
            tenant = f"\nTenant: {self._config['tenant_name']}"
            if self._config.get("tenant_lockdown"):
                tenant += " (LOCKDOWN MODE)"
        return info + active_win + tenant

    def build_app_context(self) -> str:
        """Build app-profile context for the system prompt."""
        from core.engine import detect_profile, wm

        try:
            windows = wm.list_windows()
            focused_title = ""
            for w in windows:
                if w.get("is_focused"):
                    focused_title = w.get("title", "")
                    break
            if not focused_title:
                return ""
            profile = detect_profile(focused_title)
            if not profile:
                return ""
            lines = [
                f"## Active App: {profile.display_name}",
                f"- Stealth compatibility: {profile.stealth_compatible}",
                f"- Preferred input method: {profile.preferred_input}",
            ]
            if profile.quirks:
                lines.append("- Quirks:")
                for q in profile.quirks:
                    lines.append(f"  - {q}")
            if profile.strategies:
                lines.append("- Suggested strategies:")
                for task, strategy in profile.strategies.items():
                    lines.append(f"  - {task}: {strategy}")
            if profile.menu_paths:
                lines.append("- Known menu paths:")
                for action, path in profile.menu_paths.items():
                    lines.append(f"  - {action}: {' → '.join(path)}")
            return "\n".join(lines)
        except Exception as exc:
            logger.warning("Failed to build app profile context: %s", exc)
            return ""

    def add_vision_message(
        self, messages: list[dict[str, Any]], screenshot_b64: str, text: str
    ) -> None:
        """Add a vision message (screenshot + text) to the conversation.

        ``capture_to_base64()`` encodes PNG by default; the media type below
        must stay in sync with the screenshot encoding or Anthropic will reject.
        """
        provider = self._config.get("provider", "")
        step = self._step_ref()
        if provider == "anthropic":
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                    ],
                    # Marker so prune_old_screenshots can find image messages.
                    "_sentinel_has_image": True,
                    "_sentinel_step": step,
                }
            )
        else:
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{screenshot_b64}",
                            },
                        },
                    ],
                    "_sentinel_has_image": True,
                    "_sentinel_step": step,
                }
            )

    def prune_old_screenshots(self, messages: list[dict[str, Any]]) -> None:
        """Drop the image bytes from older screenshot messages, but PRESERVE
        any text in those messages (which often includes the original goal!).

        Earlier versions of this method replaced the whole message with a
        text stub — that erased the user's goal from the first message and
        the agent forgot what it was supposed to do. We now extract the text
        block and only discard the image payload.
        """
        keep = max(1, self._image_history)
        image_indices = [i for i, m in enumerate(messages) if m.get("_sentinel_has_image")]
        if len(image_indices) <= keep:
            return
        to_strip = image_indices[: len(image_indices) - keep]
        for idx in to_strip:
            msg = messages[idx]
            step = msg.get("_sentinel_step", "?")

            # Pull any plain-text content out of the vision message's
            # content-block list before we drop the image.
            preserved_text = ""
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        preserved_text = block.get("text", "")
                        break
            elif isinstance(content, str):
                preserved_text = content

            stub = f"[screenshot at step {step} omitted to save tokens]"
            new_content = f"{preserved_text}\n{stub}" if preserved_text else stub
            messages[idx] = {"role": "user", "content": new_content}
