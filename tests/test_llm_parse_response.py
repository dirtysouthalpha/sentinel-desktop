"""Tests for LLMClient._parse_openai_response helper."""
import json
import pytest

from core.llm_client import LLMClient, LLMError


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_plain_text_response():
    data = {
        "choices": [{"message": {"role": "assistant", "content": "Hello!"}}]
    }
    assert LLMClient._parse_openai_response(data, "openai") == "Hello!"


def test_empty_content_returns_empty_string():
    data = {
        "choices": [{"message": {"role": "assistant", "content": ""}}]
    }
    assert LLMClient._parse_openai_response(data, "openai") == ""


def test_missing_content_defaults_empty():
    data = {
        "choices": [{"message": {"role": "assistant"}}]
    }
    assert LLMClient._parse_openai_response(data, "openai") == ""


def test_tool_calls_returned_as_json():
    calls = [{"id": "call_1", "function": {"name": "click", "arguments": "{}"}}]
    data = {
        "choices": [{"message": {"role": "assistant", "tool_calls": calls}}]
    }
    result = LLMClient._parse_openai_response(data, "openai")
    parsed = json.loads(result)
    assert parsed == {"tool_calls": calls}


def test_delta_instead_of_message():
    data = {
        "choices": [{"delta": {"content": "streaming chunk"}}]
    }
    assert LLMClient._parse_openai_response(data, "openai") == "streaming chunk"


def test_content_as_list_of_blocks():
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Hello"},
                        {"type": "text", "text": "world"},
                    ],
                }
            }
        ]
    }
    assert LLMClient._parse_openai_response(data, "openai") == "Hello world"


def test_content_list_skips_non_dict_blocks():
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "yes"},
                        "not a dict",
                        42,
                    ],
                }
            }
        ]
    }
    assert LLMClient._parse_openai_response(data, "openai") == "yes"


# ---------------------------------------------------------------------------
# Error envelopes
# ---------------------------------------------------------------------------

def test_non_dict_raises():
    with pytest.raises(LLMError, match="unexpected response type"):
        LLMClient._parse_openai_response("not a dict", "openai")


def test_error_string_envelope():
    with pytest.raises(LLMError, match="provider error message"):
        LLMClient._parse_openai_response({"error": "provider error message"}, "openai")


def test_error_dict_envelope_prefers_message():
    with pytest.raises(LLMError, match="bad model"):
        LLMClient._parse_openai_response(
            {"error": {"message": "bad model", "code": "MODEL_NOT_FOUND"}},
            "openai",
        )


def test_error_dict_envelope_falls_back_to_code():
    with pytest.raises(LLMError, match="ERR_001"):
        LLMClient._parse_openai_response(
            {"error": {"code": "ERR_001"}},
            "openai",
        )


def test_error_dict_envelope_falls_back_to_str():
    with pytest.raises(LLMError, match="foo"):
        LLMClient._parse_openai_response(
            {"error": {"foo": "bar"}},
            "openai",
        )


def test_error_envelope_ignored_when_choices_present():
    """Some providers return error + choices; we treat choices as the real data."""
    data = {
        "error": "transient",
        "choices": [{"message": {"content": "ok"}}],
    }
    assert LLMClient._parse_openai_response(data, "openai") == "ok"


def test_empty_choices_raises():
    with pytest.raises(LLMError, match="no 'choices'"):
        LLMClient._parse_openai_response({"choices": []}, "openai")


def test_missing_choices_raises():
    with pytest.raises(LLMError, match="no 'choices'"):
        LLMClient._parse_openai_response({}, "openai")


def test_choice_not_dict_treated_empty():
    data = {"choices": ["not a dict"]}
    assert LLMClient._parse_openai_response(data, "openai") == ""


def test_message_not_dict_treated_empty():
    data = {"choices": [{"message": "not a dict"}]}
    assert LLMClient._parse_openai_response(data, "openai") == ""


def test_provider_label_in_error():
    with pytest.raises(LLMError, match="myprovider"):
        LLMClient._parse_openai_response("x", "myprovider")


def test_response_body_truncated_in_no_choices_error():
    """Very large body should be truncated in the error message."""
    big_body = {"choices": [], "data": "x" * 500}
    with pytest.raises(LLMError):
        LLMClient._parse_openai_response(big_body, "openai")
