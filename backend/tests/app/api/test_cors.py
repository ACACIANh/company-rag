from fastapi.testclient import TestClient

from app.api.chat import app


def test_cors_preflight_allows_configured_origin():
    client = TestClient(app)
    response = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_preflight_blocks_unknown_origin():
    client = TestClient(app)
    response = client.options(
        "/chat",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert "access-control-allow-origin" not in response.headers
