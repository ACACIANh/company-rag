from fastapi.testclient import TestClient
from app.api.chat import app


def _admin_token(client: TestClient) -> str:
    return client.post(
        "/auth/token", json={"username": "admin", "password": "admin123"}
    ).json()["access_token"]


def _user_token(client: TestClient) -> str:
    return client.post(
        "/auth/token", json={"username": "joohwan", "password": "joohwan123"}
    ).json()["access_token"]


def test_admin_index_status_requires_admin():
    client = TestClient(app)
    token = _user_token(client)
    res = client.get("/admin/index/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_admin_index_status_returns_count():
    client = TestClient(app)
    token = _admin_token(client)
    res = client.get("/admin/index/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert "chunk_count" in data


def test_admin_users_returns_list():
    client = TestClient(app)
    token = _admin_token(client)
    res = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_admin_cost_report_returns_list():
    client = TestClient(app)
    token = _admin_token(client)
    res = client.get("/admin/cost/report", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert isinstance(res.json(), list)
