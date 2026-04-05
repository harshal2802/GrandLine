from httpx import AsyncClient


async def test_health_returns_200(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


async def test_health_returns_expected_shape(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "grandline-api"
    assert data["version"] == "0.1.0"
