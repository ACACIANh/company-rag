from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from shared.models import Answer, SourceRef


def _get_token(client: TestClient) -> str:
    res = client.post("/auth/token", json={"username": "alice", "password": "alice123"})
    return res.json()["access_token"]


def test_chat_returns_200():
    from app.api.chat import app
    mock_answer = Answer(text="답변", sources=[SourceRef(source="doc.md")])
    with patch("app.api.chat.answer_question", AsyncMock(return_value=mock_answer)):
        client = TestClient(app)
        token = _get_token(client)
        response = client.post(
            "/chat",
            json={"question": "테스트"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200


def test_chat_response_shape():
    from app.api.chat import app
    mock_answer = Answer(text="답변 내용", sources=[SourceRef(source="a.md"), SourceRef(source="b.md")])
    with patch("app.api.chat.answer_question", AsyncMock(return_value=mock_answer)):
        client = TestClient(app)
        token = _get_token(client)
        data = client.post(
            "/chat",
            json={"question": "질문"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
    assert data["answer"] == "답변 내용"
    assert data["sources"] == ["a.md", "b.md"]


def test_chat_response_includes_session_id():
    from app.api.chat import app
    mock_answer = Answer(text="답변", sources=[SourceRef(source="doc.md")])
    with patch("app.api.chat.answer_question", AsyncMock(return_value=mock_answer)):
        client = TestClient(app)
        token = _get_token(client)
        data = client.post(
            "/chat",
            json={"question": "질문"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
    assert "session_id" in data
    assert isinstance(data["session_id"], str)
    assert len(data["session_id"]) > 0


def test_chat_uses_provided_session_id():
    from app.api.chat import app
    mock_answer = Answer(text="답변", sources=[])
    mock_session = AsyncMock()
    mock_session.list_sessions = AsyncMock(
        return_value=[MagicMock(thread_id="my-session-123")]
    )
    mock_session.create_session = AsyncMock()
    mock_session.add_message = AsyncMock()
    app.state.session_store = mock_session

    with patch("app.api.chat.answer_question", AsyncMock(return_value=mock_answer)) as mock_aq:
        client = TestClient(app)
        token = _get_token(client)
        data = client.post(
            "/chat",
            json={"question": "질문", "session_id": "my-session-123"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()

    assert data["session_id"] == "my-session-123"
    call_config = mock_aq.call_args[1]["config"]
    assert call_config["configurable"]["thread_id"] == "user-alice:my-session-123"


def test_chat_generates_new_session_id_when_not_provided():
    from app.api.chat import app
    mock_answer = Answer(text="답변", sources=[])
    with patch("app.api.chat.answer_question", AsyncMock(return_value=mock_answer)):
        client = TestClient(app)
        token = _get_token(client)
        resp1 = client.post(
            "/chat", json={"question": "q1"}, headers={"Authorization": f"Bearer {token}"}
        ).json()
        resp2 = client.post(
            "/chat", json={"question": "q2"}, headers={"Authorization": f"Bearer {token}"}
        ).json()
    assert resp1["session_id"] != resp2["session_id"]


def test_chat_returns_403_for_unauthorized_session_id():
    from app.api.chat import app
    mock_session = AsyncMock()
    mock_session.list_sessions = AsyncMock(return_value=[])
    app.state.session_store = mock_session

    client = TestClient(app)
    token = _get_token(client)
    response = client.post(
        "/chat",
        json={"question": "질문", "session_id": "other-user-session"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
