"""Tests for AgentEngine._parse_action across the formats LLMs return."""
import json

import pytest

from core.engine import AgentEngine, _find_balanced_json_with_key


def parse(text):
    return AgentEngine()._parse_action(text)


def test_parse_plain_json_action():
    out = parse('{"action": "click", "x": 100, "y": 200}')
    assert out == {"action": "click", "x": 100, "y": 200}


def test_parse_markdown_fenced_json():
    out = parse("""Here's the action:
```json
{"action": "type_text", "text": "hello"}
```
""")
    assert out == {"action": "type_text", "text": "hello"}


def test_parse_json_with_nested_braces():
    """The old regex broke on nested braces; the balanced scanner must not."""
    text = 'sure: {"action":"open_app","path":"C:\\\\app.exe","extra":{"k":"v"}}'
    out = parse(text)
    assert out["action"] == "open_app"
    assert out["path"] == "C:\\app.exe"


def test_parse_openai_tool_calls_envelope():
    payload = json.dumps({
        "tool_calls": [{
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "hotkey",
                "arguments": json.dumps({"keys": ["ctrl", "c"]}),
            },
        }],
    })
    out = parse(payload)
    assert out == {"action": "hotkey", "keys": ["ctrl", "c"]}


def test_parse_anthropic_style_tool_call():
    # LLMClient normalises Anthropic tool_use blocks into the OpenAI envelope.
    payload = json.dumps({
        "tool_calls": [{
            "id": "x",
            "type": "function",
            "function": {
                "name": "finish",
                "arguments": json.dumps({"summary": "all done"}),
            },
        }],
    })
    out = parse(payload)
    assert out["action"] == "finish"
    assert out["summary"] == "all done"


def test_parse_returns_none_on_garbage():
    assert parse("I'm sorry, I cannot help.") is None
    assert parse("") is None


def test_balanced_json_scanner_skips_braces_in_strings():
    src = 'noise {"action":"note","text":"this has {braces} inside"}'
    obj = _find_balanced_json_with_key(src, "action")
    assert obj["action"] == "note"
    assert obj["text"] == "this has {braces} inside"
