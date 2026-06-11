import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.core.config import Settings
from app.main import app
from app.services.external_result import (
    ExternalServiceInvalidResponseError,
    ExternalServiceTimeoutError,
    ExternalServiceUnavailableError,
)


class FakeConnection:
    def __init__(self) -> None:
        self.executed_queries: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> str:
        self.executed_queries.append((query, args))
        return "INSERT 0 1"


class FakeAcquireContext:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        return None


class FakePool:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    def acquire(self) -> FakeAcquireContext:
        return FakeAcquireContext(self.connection)


def test_query_returns_result_and_saves_request(  # noqa: ANN001
    monkeypatch,
    authenticated_user,
) -> None:
    async def fake_fetch_external_result(payload, settings) -> bool:  # noqa: ANN001
        assert payload.cadastral_number == "77:01:0004012:2054"
        assert settings.external_service_url == "http://external-service:8001"
        return True

    pool = FakePool()
    app.state.db_pool = pool
    app.state.settings = Settings(
        database_url="postgresql://postgres:postgres@db:5432/test",
        external_service_url="http://external-service:8001",
    )
    monkeypatch.setattr(routes, "fetch_external_result", fake_fetch_external_result)
    client = TestClient(app)

    response = client.post(
        "/query",
        json={
            "cadastral_number": "77:01:0004012:2054",
            "latitude": 55.7558,
            "longitude": 37.6173,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"result": True}
    assert len(pool.connection.executed_queries) == 1

    query, args = pool.connection.executed_queries[0]
    assert "INSERT INTO request_history" in query
    assert args == (123, "77:01:0004012:2054", 55.7558, 37.6173, True)


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (
            ExternalServiceUnavailableError(),
            502,
            "External service is unavailable.",
        ),
        (
            ExternalServiceTimeoutError(),
            504,
            "External service request timed out.",
        ),
        (
            ExternalServiceInvalidResponseError(),
            502,
            "External service returned an invalid response.",
        ),
    ],
)
def test_query_handles_external_service_errors(
    monkeypatch,  # noqa: ANN001
    authenticated_user,  # noqa: ANN001
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    async def fake_fetch_external_result(payload, settings) -> bool:  # noqa: ANN001
        raise error

    pool = FakePool()
    app.state.db_pool = pool
    app.state.settings = Settings(
        database_url="postgresql://postgres:postgres@db:5432/test",
    )
    monkeypatch.setattr(routes, "fetch_external_result", fake_fetch_external_result)
    client = TestClient(app)

    response = client.post(
        "/query",
        json={
            "cadastral_number": "77:01:0004012:2054",
            "latitude": 55.7558,
            "longitude": 37.6173,
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert pool.connection.executed_queries == []


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        (
            {
                "cadastral_number": "77-01-0004012-2054",
                "latitude": 55.7558,
                "longitude": 37.6173,
            },
            "Cadastral number must contain four numeric parts",
        ),
        (
            {
                "cadastral_number": "77:01:0004012:2054",
                "latitude": 90.1,
                "longitude": 37.6173,
            },
            "Latitude must be a finite number between -90 and 90",
        ),
        (
            {
                "cadastral_number": "77:01:0004012:2054",
                "latitude": 55.7558,
                "longitude": 180.1,
            },
            "Longitude must be a finite number between -180 and 180",
        ),
    ],
)
def test_query_rejects_invalid_payload(
    authenticated_user,  # noqa: ANN001
    payload: dict[str, object],
    expected_error: str,
) -> None:
    pool = FakePool()
    app.state.db_pool = pool
    client = TestClient(app)

    response = client.post("/query", json=payload)

    assert response.status_code == 422
    assert expected_error in str(response.json())
    assert pool.connection.executed_queries == []
