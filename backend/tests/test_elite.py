import pytest
import time
from fastapi.testclient import TestClient
from core.guard import prompt_guard
from core.cache import smart_cache

def test_prompt_guard_blocks_dangerous_sql():
    is_safe, reason = prompt_guard.is_safe("DROP TABLE users")
    assert is_safe is False
    assert "no permitida" in reason

def test_prompt_guard_blocks_data_deletion():
    is_safe, reason = prompt_guard.is_safe("Elimina todos los registros de la base de datos")
    assert is_safe is False
    assert "peliogrosos" in reason or "seguridad" in reason

def test_smart_cache_logic():
    prompt = "Test cache query"
    model = "test-model"
    params = {"temp": 0.7}
    session = "user_1"
    response = "Cached response"
    
    # Set cache
    smart_cache.set(prompt, model, params, session, response)
    
    # Get cache - Same params
    cached = smart_cache.get(prompt, model, params, session)
    assert cached == response
    
    # Get cache - Different params (should miss)
    cached_diff = smart_cache.get(prompt, model, {"temp": 0.8}, session)
    assert cached_diff is None

@pytest.mark.asyncio
async def test_health_deep_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "dependencies" in data
    assert data["dependencies"]["database"]["status"] == "ok"
    assert "latency_ms" in data["dependencies"]["database"]
