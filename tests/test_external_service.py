from fastapi.testclient import TestClient

from external_service import main


def test_external_service_result_returns_boolean(monkeypatch) -> None:  # noqa: ANN001
    configured_delay = 0.25

    async def fake_sleep(delay: float) -> None:
        assert delay == configured_delay

    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)
    main.app.dependency_overrides[main.get_settings] = (
        lambda: main.ExternalServiceSettings(result_delay_seconds=configured_delay)
    )
    client = TestClient(main.app)

    try:
        response = client.post(
            "/result",
            json={
                "cadastral_number": "77:01:0004012:2054",
                "latitude": 55.7558,
                "longitude": 37.6173,
            },
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert isinstance(response.json()["result"], bool)


def test_external_service_delay_has_safe_local_default(
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.delenv("EXTERNAL_SERVICE_RESULT_DELAY_SECONDS", raising=False)

    settings = main.ExternalServiceSettings(_env_file=None)

    assert settings.result_delay_seconds == 0.1


def test_external_service_delay_can_be_configured_from_env(
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setenv("EXTERNAL_SERVICE_RESULT_DELAY_SECONDS", "1.5")

    settings = main.ExternalServiceSettings(_env_file=None)

    assert settings.result_delay_seconds == 1.5


def test_external_service_ping_returns_ok() -> None:
    client = TestClient(main.app)

    response = client.get("/ping")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
