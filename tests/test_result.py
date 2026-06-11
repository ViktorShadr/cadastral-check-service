from fastapi.testclient import TestClient

from app.api import routes
from app.main import app


def test_get_result_returns_boolean(monkeypatch) -> None:  # noqa: ANN001
    async def fake_sleep(delay: float) -> None:
        assert delay == routes.RESULT_DELAY_SECONDS

    monkeypatch.setattr(routes.asyncio, "sleep", fake_sleep)
    client = TestClient(app)

    response = client.get("/result")

    assert response.status_code == 200
    assert isinstance(response.json(), bool)


def test_post_result_returns_boolean(monkeypatch) -> None:  # noqa: ANN001
    async def fake_sleep(delay: float) -> None:
        assert delay == routes.RESULT_DELAY_SECONDS

    monkeypatch.setattr(routes.asyncio, "sleep", fake_sleep)
    client = TestClient(app)

    response = client.post("/result")

    assert response.status_code == 200
    assert isinstance(response.json(), bool)
