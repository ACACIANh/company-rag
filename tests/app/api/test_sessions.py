# tests/app/api/test_sessions.py
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from shared.models import Answer
from shared.session.adapters.memory import InMemorySessionStore


def _token(client: TestClient) -> str:
    res = client.post("/auth/token", json={"username": "alice", "password": "alice123"})
    return res.json()["access_token"]


def test_list_sessions_empty():
    store = InMemorySessionStore()
    with (
        patch("app.api.chat.answer_question", return_value=Answer(text="답변", sources=["doc.md"])),
        patch("app.api.chat.get_graph", return_value=MagicMock()),
        patch("app.api.deps._session_store", store),
    ):
        from app.api.chat import app
        client = TestClient(app)
        token = _token(client)
        res = client.get("/sessions", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json() == []


def test_list_sessions_after_chat():
    store = InMemorySessionStore()
    mock_answer = Answer(text="답변", sources=["doc.md"])
    with (
        patch("app.api.chat.answer_question", return_value=mock_answer),
        patch("app.api.chat.get_graph", return_value=MagicMock()),
        patch("app.api.deps._session_store", store),
    ):
        from app.api.chat import app
        client = TestClient(app)
        token = _token(client)
        client.post("/chat", json={"question": "안녕하세요"}, headers={"Authorization": f"Bearer {token}"})
        sessions = client.get("/sessions", headers={"Authorization": f"Bearer {token}"}).json()
        assert len(sessions) == 1
        assert sessions[0]["title"] == "안녕하세요"[:20]


def test_get_messages_returns_history():
    store = InMemorySessionStore()
    mock_answer = Answer(text="답변", sources=["doc.md"])
    with (
        patch("app.api.chat.answer_question", return_value=mock_answer),
        patch("app.api.chat.get_graph", return_value=MagicMock()),
        patch("app.api.deps._session_store", store),
    ):
        from app.api.chat import app
        client = TestClient(app)
        token = _token(client)
        chat_res = client.post(
            "/chat", json={"question": "질문입니다"}, headers={"Authorization": f"Bearer {token}"}
        ).json()
        msgs = client.get(
            f"/sessions/{chat_res['session_id']}/messages",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"


def test_get_messages_404_for_other_user():
    store = InMemorySessionStore()
    store.create_session("other-session", "bob", "밥의 질문")
    mock_answer = Answer(text="답변", sources=[])
    with (
        patch("app.api.chat.answer_question", return_value=mock_answer),
        patch("app.api.chat.get_graph", return_value=MagicMock()),
        patch("app.api.deps._session_store", store),
    ):
        from app.api.chat import app
        client = TestClient(app)
        token = _token(client)  # alice
        res = client.get(
            "/sessions/other-session/messages",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 404


def test_delete_session():
    store = InMemorySessionStore()
    mock_answer = Answer(text="답변", sources=["doc.md"])
    with (
        patch("app.api.chat.answer_question", return_value=mock_answer),
        patch("app.api.chat.get_graph", return_value=MagicMock()),
        patch("app.api.deps._session_store", store),
    ):
        from app.api.chat import app
        client = TestClient(app)
        token = _token(client)
        chat_res = client.post(
            "/chat", json={"question": "삭제할 질문"}, headers={"Authorization": f"Bearer {token}"}
        ).json()
        session_id = chat_res["session_id"]
        res = client.delete(f"/sessions/{session_id}", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 204
        sessions = client.get("/sessions", headers={"Authorization": f"Bearer {token}"}).json()
        assert sessions == []


def test_delete_session_404_for_other_user():
    store = InMemorySessionStore()
    store.create_session("other-session", "bob", "밥의 질문")
    mock_answer = Answer(text="답변", sources=[])
    with (
        patch("app.api.chat.answer_question", return_value=mock_answer),
        patch("app.api.chat.get_graph", return_value=MagicMock()),
        patch("app.api.deps._session_store", store),
    ):
        from app.api.chat import app
        client = TestClient(app)
        token = _token(client)  # alice
        res = client.delete(
            "/sessions/other-session", headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 404
