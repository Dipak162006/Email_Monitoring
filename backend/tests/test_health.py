import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_endpoint(async_client: AsyncClient):
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_ping_endpoint(async_client: AsyncClient):
    response = await async_client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "pong"}

    v1_response = await async_client.get("/api/v1/ping")
    assert v1_response.status_code == 200
    assert v1_response.json() == {"status": "pong"}


@pytest.mark.asyncio
async def test_health_endpoint(async_client: AsyncClient):
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["ok", "degraded"]
    assert "services" in data
    assert "database" in data["services"]
    assert "redis" in data["services"]
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_openapi_schema(async_client: AsyncClient):
    response = await async_client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Email Monitoring System"
    assert "/api/v1/health" in schema["paths"]
