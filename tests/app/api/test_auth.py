from fastapi.testclient import TestClient
from app.api.chat import app


def test_login_success():
    res = TestClient(app).post("/auth/token", json={"username": "alice", "password": "alice123"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password():
    res = TestClient(app).post("/auth/token", json={"username": "alice", "password": "wrong"})
    assert res.status_code == 401


def test_me_with_valid_token():
    client = TestClient(app)
    token = client.post("/auth/token", json={"username": "alice", "password": "alice123"}).json()["access_token"]
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["user_id"] == "user-alice"


def test_chat_without_token_returns_401():
    res = TestClient(app).post("/chat", json={"question": "테스트"})
    assert res.status_code == 401
