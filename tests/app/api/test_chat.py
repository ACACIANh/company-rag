from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from shared.models import Answer
from shared.session.base import SessionMeta


def _get_token(client: TestClient) -> str:
    res = client.post("/auth/token", json={"username": "alice", "password": "alice123"})
    return res.json()["access_token"]


def _owned_store(session_ids: list[str]) -> MagicMock:
    """list_sessions가 주어진 session_id를 소유한 것으로 응답하는 mock store."""
    mock_store = MagicMock()
    mock_store.list_sessions.return_value = [
        MagicMock(thread_id=sid) for sid in session_ids
    ]
    return mock_store


def test_chat_returns_200():
    mock_answer = Answer(text="답변", sources=["doc.md"])
    with patch("app.api.chat.answer_question", return_value=mock_answer), \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        token = _get_token(client)
        response = client.post(
            "/chat",
            json={"question": "테스트"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200


def test_chat_response_shape():
    mock_answer = Answer(text="답변 내용", sources=["a.md", "b.md"])
    with patch("app.api.chat.answer_question", return_value=mock_answer), \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
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
    mock_answer = Answer(text="답변", sources=["doc.md"])
    with patch("app.api.chat.answer_question", return_value=mock_answer), \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
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
    """클라이언트가 session_id를 넘기면 응답에 그대로 반환되고,
    MemorySaver에는 user_id가 앞에 붙은 thread_id로 전달된다."""
    mock_answer = Answer(text="답변", sources=[])
    mock_store = _owned_store(["my-session-123"])
    with patch("app.api.chat.answer_question", return_value=mock_answer) as mock_aq, \
         patch("app.api.chat.get_graph", return_value=MagicMock()), \
         patch("app.api.chat.get_session_store", return_value=mock_store):
        from app.api.chat import app
        client = TestClient(app)
        token = _get_token(client)
        data = client.post(
            "/chat",
            json={"question": "질문", "session_id": "my-session-123"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
    # 클라이언트에게 반환하는 session_id는 원본 UUID
    assert data["session_id"] == "my-session-123"
    # answer_question에 전달되는 thread_id는 {user_id}:{session_id}
    call_config = mock_aq.call_args[1]["config"]
    assert call_config["configurable"]["thread_id"] == "user-alice:my-session-123"


def test_chat_generates_new_session_id_when_not_provided():
    mock_answer = Answer(text="답변", sources=[])
    with patch("app.api.chat.answer_question", return_value=mock_answer), \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        token = _get_token(client)
        resp1 = client.post(
            "/chat",
            json={"question": "q1"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        resp2 = client.post(
            "/chat",
            json={"question": "q2"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
    assert resp1["session_id"] != resp2["session_id"]


def test_chat_returns_403_for_unauthorized_session_id():
    """다른 사용자의 session_id를 넘기면 403을 반환한다."""
    mock_store = _owned_store([])  # alice가 소유한 세션 없음
    with patch("app.api.chat.get_graph", return_value=MagicMock()), \
         patch("app.api.chat.get_session_store", return_value=mock_store):
        from app.api.chat import app
        client = TestClient(app)
        token = _get_token(client)
        response = client.post(
            "/chat",
            json={"question": "질문", "session_id": "other-user-session"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403
