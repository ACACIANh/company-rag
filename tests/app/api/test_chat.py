from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from shared.models import Answer


def test_chat_returns_200():
    mock_answer = Answer(text="답변", sources=["doc.md"])
    with patch("app.api.chat.answer_question", return_value=mock_answer), \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        response = client.post("/chat", json={"question": "테스트"})
    assert response.status_code == 200


def test_chat_response_shape():
    mock_answer = Answer(text="답변 내용", sources=["a.md", "b.md"])
    with patch("app.api.chat.answer_question", return_value=mock_answer), \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        data = client.post("/chat", json={"question": "질문"}).json()
    assert data["answer"] == "답변 내용"
    assert data["sources"] == ["a.md", "b.md"]


def test_chat_response_includes_session_id():
    mock_answer = Answer(text="답변", sources=["doc.md"])
    with patch("app.api.chat.answer_question", return_value=mock_answer), \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        data = client.post("/chat", json={"question": "질문"}).json()
    assert "session_id" in data
    assert isinstance(data["session_id"], str)
    assert len(data["session_id"]) > 0


def test_chat_uses_provided_session_id():
    mock_answer = Answer(text="답변", sources=[])
    with patch("app.api.chat.answer_question", return_value=mock_answer) as mock_aq, \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        data = client.post("/chat", json={"question": "질문", "session_id": "my-session-123"}).json()
    assert data["session_id"] == "my-session-123"
    # answer_question이 올바른 config로 호출되었는지 확인
    call_config = mock_aq.call_args[1]["config"]
    assert call_config["configurable"]["thread_id"] == "my-session-123"


def test_chat_generates_new_session_id_when_not_provided():
    mock_answer = Answer(text="답변", sources=[])
    with patch("app.api.chat.answer_question", return_value=mock_answer) as mock_aq, \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        resp1 = client.post("/chat", json={"question": "q1"}).json()
        resp2 = client.post("/chat", json={"question": "q2"}).json()
    # session_id가 없으면 매 요청마다 새 UUID 생성
    assert resp1["session_id"] != resp2["session_id"]
