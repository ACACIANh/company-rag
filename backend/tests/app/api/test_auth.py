from fastapi.testclient import TestClient
from app.api.chat import app


def test_login_success():
    res = TestClient(app).post("/auth/token", json={"username": "jisoo", "password": "jisoo123"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password():
    res = TestClient(app).post("/auth/token", json={"username": "jisoo", "password": "wrong"})
    assert res.status_code == 401


def test_me_with_valid_token():
    client = TestClient(app)
    token = client.post("/auth/token", json={"username": "jisoo", "password": "jisoo123"}).json()["access_token"]
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["user_id"] == "user-jisoo"


def test_chat_without_token_returns_401():
    res = TestClient(app).post("/chat", json={"question": "테스트"})
    assert res.status_code == 401


def test_me_returns_departments_for_김지수():
    client = TestClient(app)
    token = client.post("/auth/token", json={"username": "jisoo", "password": "jisoo123"}).json()["access_token"]
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert "departments" in data
    assert data["departments"] == ["개발"]


def test_me_returns_departments_for_admin():
    client = TestClient(app)
    token = client.post("/auth/token", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    # admin 은 부서 대신 c_level FGA 역할로 전사 열람(super_reader). 부서 소속 없음.
    assert data["departments"] == []
