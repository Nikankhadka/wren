import httpx
import pytest

from app.main import app


@pytest.mark.anyio
async def test_health() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:3000",
        "http://bytefix.localhost:3000",
        "http://admin.localhost:3000",
        "https://bytefix.wren.app",
        "https://app.wren.app",
    ],
)
async def test_cors_allows_frontend_origins(origin: str) -> None:
    """T-011: frontend and backend are always different origins (every
    tenant gets its own subdomain) - a browser fetch from any of them must
    not be silently blocked by a missing CORS header."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/chat",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )
    assert response.headers.get("access-control-allow-origin") == origin


@pytest.mark.anyio
async def test_cors_rejects_unrelated_origins() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/chat",
            headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"},
        )
    assert "access-control-allow-origin" not in response.headers
