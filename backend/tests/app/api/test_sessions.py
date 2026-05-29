from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from shared.models import Answer, SourceRef
from shared.session.adapters.memory import InMemorySessionStore


def _token(client: TestClient) -> str:
    res = client.post("/auth/token", json={"username": "alice", "password": "alice123"})
    return res.json()["access_token"]


def test_list_sessions_empty():
    from app.api.chat import app
    # conftest의 default mock_session은 list_sessions → [] 이므로 별도 설정 불필요
    client = TestClient(app)
    token = _token(client)
    res = client.get("/sessions", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json() == []


def test_list_sessions_after_chat():
    from app.api.chat import app
    store = InMemorySessionStore()
    app.state.session_store = store

    mock_answer = Answer(text="답변", sources=[SourceRef(source="doc.md")])
    with patch("app.api.chat.answer_question", AsyncMock(return_value=mock_answer)):
        client = TestClient(app)
        token = _token(client)
        client.post("/chat", json={"question": "안녕하세요"}, headers={"Authorization": f"Bearer {token}"})
        sessions = client.get("/sessions", headers={"Authorization": f"Bearer {token}"}).json()
    assert len(sessions) == 1
    assert sessions[0]["title"] == "안녕하세요"[:20]


def test_get_messages_returns_history():
    from app.api.chat import app
    store = InMemorySessionStore()
    app.state.session_store = store

    mock_answer = Answer(text="답변", sources=[SourceRef(source="doc.md")])
    with patch("app.api.chat.answer_question", AsyncMock(return_value=mock_answer)):
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


async def test_get_messages_404_for_other_user():
    from app.api.chat import app
    store = InMemorySessionStore()
    await store.create_session("other-session", "bob", "밥의 질문")
    app.state.session_store = store

    client = TestClient(app)
    token = _token(client)  # alice
    res = client.get(
        "/sessions/other-session/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


def test_delete_session():
    from app.api.chat import app
    store = InMemorySessionStore()
    app.state.session_store = store

    mock_answer = Answer(text="답변", sources=[SourceRef(source="doc.md")])
    with patch("app.api.chat.answer_question", AsyncMock(return_value=mock_answer)):
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


async def test_delete_session_404_for_other_user():
    from app.api.chat import app
    store = InMemorySessionStore()
    await store.create_session("other-session", "bob", "밥의 질문")
    app.state.session_store = store

    client = TestClient(app)
    token = _token(client)  # alice
    res = client.delete(
        "/sessions/other-session", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 404


async def test_get_messages_filters_inaccessible_sources():
    """권한이 취소된 문서 source는 세션 이력 로드 시 제거된다."""
    from app.api.chat import app
    store = InMemorySessionStore()
    await store.create_session("sess1", "user-alice", "질문")
    await store.add_message("sess1", "user", "질문입니다", [])
    await store.add_message(
        "sess1",
        "assistant",
        "답변입니다",
        [
            SourceRef(source="pub.md", sensitivity="public"),
            SourceRef(source="secret.md", sensitivity="internal", team_id="team:restricted"),
        ],
    )
    app.state.session_store = store

    alice_teams = ["team:general"]

    async def _filtered_filter(sources, uid):
        return [
            s for s in sources
            if s.sensitivity == "public"
            or (s.sensitivity == "internal" and s.team_id in alice_teams)
        ]

    mock_fga = MagicMock()
    mock_fga.filter_sources = AsyncMock(side_effect=_filtered_filter)
    app.state.fga_client = mock_fga

    client = TestClient(app)
    token = _token(client)
    msgs = client.get(
        "/sessions/sess1/messages",
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    assert len(msgs) == 2
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["sources"] == ["pub.md"]
