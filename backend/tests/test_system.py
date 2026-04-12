from fastapi.testclient import TestClient

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "queue_depth" in data
    assert "workers_alive" in data

def test_root_not_found(client: TestClient):
    # Test that global error handler works for 404/others if not handled
    response = client.get("/non-existent-path")
    # FastAPI handles 404 by default unless we catch it
    assert response.status_code == 404
