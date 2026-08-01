"""The endpoints the Command Center has been calling into a void since v8.

``/api/files``, ``/api/files/content``, ``/api/files/download`` and
``/api/conversations`` were all 404 — no handler existed anywhere in
``api/server.py`` — so the dashboard's file explorer showed "Cannot list
directory" on every load and its conversation sidebar was permanently empty.

``tests/test_filesystem_jail.py`` proves the jail itself. This proves the
*wiring*: that the refusals survive the trip through HTTP with their status
codes intact, that auth is enforced, and that a conversation actually persists.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

import api.server as mod
from config import Config
from core import conversations as convmod
from core import filesystem as fsmod

TOKEN = "dashboard-backend-test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A live app with a real jail and a throwaway conversation database."""
    root = tmp_path / "jail"
    (root / "sub").mkdir(parents=True)
    (root / "hello.txt").write_text("hello from inside", encoding="utf-8")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("SENTINEL_API_TOKEN=hunter2", encoding="utf-8")

    monkeypatch.setenv(mod.API_TOKEN_ENV, TOKEN)
    monkeypatch.setenv(fsmod.ROOTS_ENV, str(root))
    monkeypatch.setenv(convmod.DB_ENV, str(tmp_path / "convs.db"))
    fsmod.allowed_roots.cache_clear()
    convmod.reset_connection()

    client = TestClient(mod.SentinelServer(Config()).create_app())
    yield client, root, outside

    fsmod.allowed_roots.cache_clear()
    convmod.reset_connection()


# ---------------------------------------------------------------------------
# The endpoints exist at all — this is the regression that matters most
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/files"),
        ("get", "/api/files/content"),
        ("get", "/api/files/download"),
        ("get", "/api/conversations"),
        ("post", "/api/conversations"),
    ],
)
def test_endpoint_is_not_404(env, method, path):
    client, root, _ = env
    resp = getattr(client, method)(path, params={"path": str(root / "hello.txt")}, headers=AUTH)
    assert resp.status_code != 404, f"{path} is still unimplemented"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/api/files", "/api/files/content", "/api/files/download", "/api/conversations"],
)
def test_unauthenticated_is_refused(env, path):
    client, root, _ = env
    assert client.get(path, params={"path": str(root)}).status_code == 401


def test_a_wrong_token_is_refused(env):
    client, root, _ = env
    resp = client.get("/api/files", params={"path": str(root)}, headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def test_listing_returns_entries_the_dashboard_can_render(env):
    client, root, _ = env
    body = client.get("/api/files", params={"path": str(root)}, headers=AUTH).json()
    names = {e["name"] for e in body["entries"]}
    assert {"hello.txt", "sub"} <= names
    for entry in body["entries"]:
        # renderFileTree() reads exactly these three.
        assert {"name", "path", "type"} <= set(entry)


def test_listing_with_no_path_opens_at_the_first_root(env):
    """The dashboard's default was a hardcoded C:\\, which the jail refuses."""
    client, root, _ = env
    body = client.get("/api/files", headers=AUTH).json()
    assert os.path.normcase(body["path"]) == os.path.normcase(str(root.resolve()))


def test_traversal_through_http_is_refused(env):
    client, root, outside = env
    resp = client.get(
        "/api/files/content",
        params={"path": str(root / ".." / "outside" / "secret.txt")},
        headers=AUTH,
    )
    assert resp.status_code == 403
    assert "hunter2" not in resp.text


def test_unc_through_http_is_refused(env):
    client, _, _ = env
    resp = client.get("/api/files", params={"path": r"\\evil\share"}, headers=AUTH)
    assert resp.status_code == 400


def test_no_roots_configured_answers_503_not_500(env, monkeypatch, tmp_path):
    """apiFetch() renders 'degraded' from a 503 and 'error' from anything else;
    a misconfigured service must land in the first bucket."""
    client, _, _ = env
    monkeypatch.setenv(fsmod.ROOTS_ENV, str(tmp_path / "nowhere"))
    fsmod.allowed_roots.cache_clear()
    resp = client.get("/api/files", params={"path": "C:\\"}, headers=AUTH)
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Content and download
# ---------------------------------------------------------------------------


def test_content_returns_the_file(env):
    client, root, _ = env
    body = client.get(
        "/api/files/content", params={"path": str(root / "hello.txt")}, headers=AUTH
    ).json()
    assert body["content"] == "hello from inside"
    assert body["is_image"] is False


def test_content_respects_max_bytes(env):
    client, root, _ = env
    (root / "big.txt").write_text("z" * 5000, encoding="utf-8")
    body = client.get(
        "/api/files/content",
        params={"path": str(root / "big.txt"), "max_bytes": 100},
        headers=AUTH,
    ).json()
    assert body["truncated"] is True
    assert len(body["content"]) <= 100


def test_download_is_an_attachment(env):
    client, root, _ = env
    resp = client.get("/api/files/download", params={"path": str(root / "hello.txt")}, headers=AUTH)
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.headers["content-type"] == "application/octet-stream"


def test_download_of_a_hostile_filename_cannot_break_the_header(env):
    client, root, _ = env
    nasty = root / 'we"ird;name.txt'
    try:
        nasty.write_text("x", encoding="utf-8")
    except OSError:
        pytest.skip("filesystem rejects this name")
    resp = client.get("/api/files/download", params={"path": str(nasty)}, headers=AUTH)
    disposition = resp.headers["content-disposition"]
    assert disposition.count('"') == 2  # exactly the pair around the filename
    assert ";" not in disposition.split("filename=")[1]


def test_download_refuses_a_directory(env):
    client, root, _ = env
    assert client.get("/api/files/download", params={"path": str(root)}, headers=AUTH).status_code == 400


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


def test_a_conversation_round_trips(env):
    client, _, _ = env
    conv = client.post("/api/conversations", headers=AUTH).json()
    conv_id = conv["id"]

    posted = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"role": "user", "content": "why is the chat empty?"},
        headers=AUTH,
    )
    assert posted.status_code == 200

    listed = client.get("/api/conversations", headers=AUTH).json()["conversations"]
    row = next(c for c in listed if c["id"] == conv_id)
    # renderConvs() reads title / updated_at / step_count.
    assert row["title"] == "why is the chat empty?"
    assert row["step_count"] == 1
    assert row["updated_at"]

    msgs = client.get(f"/api/conversations/{conv_id}/messages", headers=AUTH).json()["messages"]
    assert [m["content"] for m in msgs] == ["why is the chat empty?"]


def test_delete_actually_deletes(env):
    """delConv() toasted 'Conversation deleted' and deleted nothing."""
    client, _, _ = env
    conv_id = client.post("/api/conversations", headers=AUTH).json()["id"]
    client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"role": "user", "content": "x"},
        headers=AUTH,
    )
    assert client.delete(f"/api/conversations/{conv_id}", headers=AUTH).status_code == 200
    assert client.get(f"/api/conversations/{conv_id}", headers=AUTH).status_code == 404
    remaining = client.get("/api/conversations", headers=AUTH).json()["conversations"]
    assert all(c["id"] != conv_id for c in remaining)


def test_messages_cascade_on_delete(env):
    client, _, _ = env
    conv_id = client.post("/api/conversations", headers=AUTH).json()["id"]
    client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"role": "user", "content": "orphan me"},
        headers=AUTH,
    )
    client.delete(f"/api/conversations/{conv_id}", headers=AUTH)
    assert convmod.messages(conv_id) == []


def test_message_for_unknown_conversation_is_404_not_an_implicit_create(env):
    client, _, _ = env
    resp = client.post(
        "/api/conversations/does-not-exist/messages",
        json={"role": "user", "content": "x"},
        headers=AUTH,
    )
    assert resp.status_code == 404
    assert client.get("/api/conversations", headers=AUTH).json()["conversations"] == []


def test_unknown_role_is_refused(env):
    client, _, _ = env
    conv_id = client.post("/api/conversations", headers=AUTH).json()["id"]
    resp = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"role": "root", "content": "x"},
        headers=AUTH,
    )
    assert resp.status_code == 400


def test_delete_of_unknown_conversation_is_404(env):
    client, _, _ = env
    assert client.delete("/api/conversations/nope", headers=AUTH).status_code == 404


def test_search_finds_a_phrase_in_a_message_body(env):
    """filterConvs() only ever matched titles."""
    client, _, _ = env
    conv_id = client.post("/api/conversations", headers=AUTH).json()["id"]
    client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"role": "user", "content": "first message becomes the title"},
        headers=AUTH,
    )
    client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"role": "assistant", "content": "the synapse reaper was the culprit"},
        headers=AUTH,
    )
    hits = client.get("/api/conversations", params={"q": "synapse reaper"}, headers=AUTH).json()
    assert [c["id"] for c in hits["conversations"]] == [conv_id]


def test_search_wildcards_are_escaped(env):
    """A bare '%' must not match everything."""
    client, _, _ = env
    conv_id = client.post("/api/conversations", headers=AUTH).json()["id"]
    client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"role": "user", "content": "no percent sign here"},
        headers=AUTH,
    )
    hits = client.get("/api/conversations", params={"q": "%"}, headers=AUTH).json()
    assert hits["conversations"] == []


def test_conversation_survives_a_new_connection(env, tmp_path):
    """The sidebar must still be populated after a restart."""
    client, _, _ = env
    conv_id = client.post("/api/conversations", headers=AUTH).json()["id"]
    client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"role": "user", "content": "persist me"},
        headers=AUTH,
    )
    convmod.reset_connection()
    assert any(c["id"] == conv_id for c in convmod.list_all())
