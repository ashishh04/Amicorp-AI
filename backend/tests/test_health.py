import asyncio

from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app, backend_options={"loop_factory": asyncio.SelectorEventLoop}) as client:
        response = client.get("/health")
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
