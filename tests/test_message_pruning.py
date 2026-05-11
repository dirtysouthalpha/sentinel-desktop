"""Tests for screenshot history pruning and message cleaning."""
import pytest

from core.engine import AgentEngine, _clean_messages_for_api


def make_image_msg(step, text="", payload="<b64>"):
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": text or f"step {step}"},
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{payload}"}},
        ],
        "_sentinel_has_image": True,
        "_sentinel_step": step,
    }


def test_prune_keeps_recent_screenshots():
    engine = AgentEngine({"image_history": 2})
    messages = [{"role": "system", "content": "sys"}]
    for i in range(5):
        messages.append(make_image_msg(i + 1))

    engine._prune_old_screenshots(messages)

    image_kept = [m for m in messages if m.get("_sentinel_has_image")]
    assert len(image_kept) == 2
    # The pruned messages become plain user text messages.
    stubs = [
        m for m in messages
        if isinstance(m.get("content"), str) and "[screenshot" in m["content"]
    ]
    assert len(stubs) == 3


def test_prune_noop_when_under_budget():
    engine = AgentEngine({"image_history": 3})
    messages = [{"role": "system", "content": "sys"}]
    for i in range(2):
        messages.append(make_image_msg(i + 1))
    before = [m.copy() for m in messages]
    engine._prune_old_screenshots(messages)
    assert messages == before


def test_prune_preserves_text_content_in_first_message():
    """Regression: pruning must NOT erase the user's original goal."""
    engine = AgentEngine({"image_history": 1})
    messages = [
        {"role": "system", "content": "sys"},
        make_image_msg(0, text="Goal: open Outlook and read the inbox"),
        make_image_msg(1, text="Step 1 result: clicked Start"),
        make_image_msg(2, text="Step 2 result: typed 'outlook'"),
    ]
    engine._prune_old_screenshots(messages)
    # Only the most recent image survives.
    image_kept = [m for m in messages if m.get("_sentinel_has_image")]
    assert len(image_kept) == 1
    # But the original goal text MUST still be in the conversation somewhere.
    serialized = " ".join(
        str(m.get("content")) if isinstance(m.get("content"), str) else
        " ".join(str(b) for b in m.get("content", []))
        for m in messages
    )
    assert "open Outlook" in serialized, \
        "pruning erased the user's goal — the agent would forget what to do"


def test_clean_messages_strips_sentinel_keys():
    msgs = [
        {"role": "system", "content": "sys"},
        {**make_image_msg(1), "extra_field": "kept"},
    ]
    out = _clean_messages_for_api(msgs)
    assert all("_sentinel_has_image" not in m for m in out)
    assert all("_sentinel_step" not in m for m in out)
    assert out[1]["extra_field"] == "kept"
    assert out[1]["role"] == "user"
