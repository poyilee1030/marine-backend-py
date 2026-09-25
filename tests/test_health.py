from fastapi.testclient import TestClient

from marine_backend.main import app


def test_health_returns_ok():
    client = TestClient(app)

    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
