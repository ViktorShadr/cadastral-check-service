from fastapi.testclient import TestClient

from external_service import main


def test_external_service_result_returns_boolean(monkeypatch) -> None:  # noqa: ANN001
    async def fake_sleep(delay: float) -> None:
        assert delay == main.RESULT_DELAY_SECONDS

    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)
    client = TestClient(main.app)

    response = client.post(
        "/result",
        json={
            "cadastral_number": "77:01:0004012:2054",
            "latitude": 55.7558,
            "longitude": 37.6173,
        },
    )

    assert response.status_code == 200
    assert isinstance(response.json()["result"], bool)


def test_external_service_result_validates_payload() -> None:
    client = TestClient(main.app)

    response = client.post(
        "/result",
        json={
            "cadastral_number": "invalid",
            "latitude": 55.7558,
            "longitude": 37.6173,
        },
    )

    assert response.status_code == 422
