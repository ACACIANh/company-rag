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
