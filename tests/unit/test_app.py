import httpx

from maestarr import __version__
from maestarr.app import app


async def test_health_returns_ok():
    # AsyncClient + ASGITransport, not TestClient: FastAPI's TestClient cannot
    # be used inside an async test function.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
