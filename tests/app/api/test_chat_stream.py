"""POST /chat/stream SSE 엔드포인트 테스트."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _get_token(client: TestClient) -> str:
    res = client.post("/auth/token", json={"username": "alice", "password": "alice123"})
    return res.json()["access_token"]


async def _fake_stream_answer(**kwargs):
    queue: asyncio.Queue = kwargs["token_queue"]
    await queue.put({"type": "token", "content": "안녕"})
    await queue.put({"type": "token", "content": "하세요"})
    await queue.put({"type": "sources", "sources": ["doc.md"]})
    await queue.put({"type": "done", "session_id": kwargs["session_id"]})


def test_chat_stream_returns_sse_events():
    from app.api.chat import app

    with patch("app.api.chat.stream_answer", side_effect=_fake_stream_answer):
        client = TestClient(app)
        token = _get_token(client)
        with client.stream(
            "POST",
            "/chat/stream",
            json={"question": "테스트"},
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            resp.read()
            lines = resp.text.strip().split("\n\n")
            events = [json.loads(line.removeprefix("data: ")) for line in lines if line.startswith("data:")]

    types = [e["type"] for e in events]
    assert "token" in types
    assert "sources" in types
    assert types[-1] == "done"


def test_chat_stream_token_content():
    from app.api.chat import app

    with patch("app.api.chat.stream_answer", side_effect=_fake_stream_answer):
        client = TestClient(app)
        token = _get_token(client)
        with client.stream(
            "POST",
            "/chat/stream",
            json={"question": "테스트"},
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            resp.read()
            lines = resp.text.strip().split("\n\n")
            events = [json.loads(line.removeprefix("data: ")) for line in lines if line.startswith("data:")]

    token_events = [e for e in events if e["type"] == "token"]
    assert [e["content"] for e in token_events] == ["안녕", "하세요"]


def test_chat_stream_returns_401_without_token():
    from app.api.chat import app
    client = TestClient(app)
    resp = client.post("/chat/stream", json={"question": "테스트"})
    assert resp.status_code == 401


def test_chat_stream_returns_403_for_foreign_session():
    from app.api.chat import app

    mock_session = AsyncMock()
    mock_session.list_sessions = AsyncMock(return_value=[])
    app.state.session_store = mock_session

    client = TestClient(app)
    token = _get_token(client)
    resp = client.post(
        "/chat/stream",
        json={"question": "테스트", "session_id": "other-session"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
