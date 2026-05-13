"""Regression test: SYSTEM_PROMPT must accept env context without choking on
the literal JSON example inside it.

Originally the engine did ``SYSTEM_PROMPT.format(env_context=env_context)``
which exploded with ``KeyError: '"action"'`` because the prompt contains the
literal text ``Example: {"action": "click", ...}`` and Python's str.format
interprets *every* set of braces as a placeholder.
"""

from core.engine import SYSTEM_PROMPT


def test_prompt_contains_env_placeholder():
    assert "{env_context}" in SYSTEM_PROMPT


def test_prompt_substitution_does_not_choke_on_json_example():
    """Substituting env context must not raise on the literal JSON braces."""
    # This is the exact replace() call the engine uses now.
    result = SYSTEM_PROMPT.replace("{env_context}", "OS: Windows 11")
    assert "OS: Windows 11" in result
    # The JSON example survives intact.
    assert '"action"' in result and '"click"' in result


def test_str_format_on_prompt_would_still_crash():
    """Document the original bug so we don't regress to .format() naively."""
    import pytest

    with pytest.raises(KeyError):
        SYSTEM_PROMPT.format(env_context="anything")
