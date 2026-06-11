from fastapi.testclient import TestClient

from app.api import routes
from app.core.config import Settings
from app.main import app


def test_get_result_returns_boolean(monkeypatch) -> None:  # noqa: ANN001
    async def fake_fetch_external_result(payload, settings) -> bool:  # noqa: ANN001
        assert payload.cadastral_number == "77:01:0004012:2054"
        assert settings.external_service_url == "http://external-service:8001"
        return True

    app.state.settings = Settings(
        database_url="postgresql://postgres:postgres@db:5432/test",
        external_service_url="http://external-service:8001",
    )
    monkeypatch.setattr(routes, "fetch_external_result", fake_fetch_external_result)
    client = TestClient(app)

    response = client.get("/result")

    assert response.status_code == 200
    assert isinstance(response.json(), bool)


def test_post_result_returns_boolean(monkeypatch) -> None:  # noqa: ANN001
    async def fake_fetch_external_result(payload, settings) -> bool:  # noqa: ANN001
        assert payload.cadastral_number == "77:01:0004012:2055"
        assert payload.latitude == 55.7559
        assert payload.longitude == 37.6174
        return False

    app.state.settings = Settings(
        database_url="postgresql://postgres:postgres@db:5432/test",
    )
    monkeypatch.setattr(routes, "fetch_external_result", fake_fetch_external_result)
    client = TestClient(app)

    response = client.post(
        "/result",
        json={
            "cadastral_number": "77:01:0004012:2055",
            "latitude": 55.7559,
            "longitude": 37.6174,
        },
    )

    assert response.status_code == 200
    assert isinstance(response.json(), bool)
