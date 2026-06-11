import math

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import routes
from app.core.config import Settings
from app.main import app
from app.schemas import QueryRequest
from external_service.main import app as external_app

VALID_PAYLOAD = {
    "cadastral_number": "77:01:0004012:2054",
    "latitude": 55.7558,
    "longitude": 37.6173,
}


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


@pytest.mark.parametrize(
    "payload",
    [
        {
            "cadastral_number": "1:2:3:4",
            "latitude": -90,
            "longitude": -180,
        },
        {
            "cadastral_number": "77:01:0004012:2054",
            "latitude": 90,
            "longitude": 180,
        },
        {
            "cadastral_number": f"{'1' * 249}:2:3:4",
            "latitude": 0,
            "longitude": 0,
        },
    ],
)
def test_query_request_accepts_valid_boundaries(payload: dict[str, object]) -> None:
    request = QueryRequest.model_validate(payload)

    assert request.cadastral_number == payload["cadastral_number"]
    assert request.latitude == payload["latitude"]
    assert request.longitude == payload["longitude"]


@pytest.mark.parametrize(
    "cadastral_number",
    [
        "",
        "77",
        "77:01:0004012",
        "77:01:0004012:2054:1",
        "77::0004012:2054",
        "77:01:abc:2054",
        "77:01:-0004012:2054",
        "77-01-0004012-2054",
        f"{'1' * 250}:2:3:4",
    ],
)
def test_query_request_rejects_invalid_cadastral_numbers(
    cadastral_number: str,
) -> None:
    payload = {**VALID_PAYLOAD, "cadastral_number": cadastral_number}

    with pytest.raises(ValidationError):
        QueryRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", -90.000001),
        ("latitude", 90.000001),
        ("latitude", math.nan),
        ("latitude", math.inf),
        ("latitude", -math.inf),
        ("longitude", -180.000001),
        ("longitude", 180.000001),
        ("longitude", math.nan),
        ("longitude", math.inf),
        ("longitude", -math.inf),
    ],
)
def test_query_request_rejects_invalid_coordinate_boundaries(
    field: str,
    value: float,
) -> None:
    payload = {**VALID_PAYLOAD, field: value}

    with pytest.raises(ValidationError):
        QueryRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cadastral_number", 770100040122054),
        ("latitude", "55.7558"),
        ("longitude", "37.6173"),
        ("latitude", True),
        ("longitude", False),
    ],
)
def test_query_request_rejects_non_json_number_coordinate_types(
    field: str,
    value: object,
) -> None:
    payload = {**VALID_PAYLOAD, field: value}

    with pytest.raises(ValidationError):
        QueryRequest.model_validate(payload)


@pytest.mark.parametrize("missing_field", ["cadastral_number", "latitude", "longitude"])
def test_query_endpoint_rejects_missing_required_fields(
    monkeypatch,  # noqa: ANN001
    missing_field: str,
) -> None:
    async def fail_if_called(payload, settings) -> bool:  # noqa: ANN001
        raise AssertionError("external service must not be called for invalid input")

    pool = FakePool()
    app.state.db_pool = pool
    app.state.settings = Settings(
        database_url="postgresql://postgres:postgres@db:5432/test",
    )
    monkeypatch.setattr(routes, "fetch_external_result", fail_if_called)
    client = TestClient(app)
    payload = {**VALID_PAYLOAD}
    payload.pop(missing_field)

    response = client.post("/query", json=payload)

    assert response.status_code == 422
    assert pool.connection.executed_queries == []


@pytest.mark.parametrize(
    "payload",
    [
        {**VALID_PAYLOAD, "cadastral_number": "77:01:0004012"},
        {**VALID_PAYLOAD, "latitude": -90.000001},
        {**VALID_PAYLOAD, "latitude": 90.000001},
        {**VALID_PAYLOAD, "longitude": -180.000001},
        {**VALID_PAYLOAD, "longitude": 180.000001},
        {**VALID_PAYLOAD, "latitude": "55.7558"},
        {**VALID_PAYLOAD, "longitude": "37.6173"},
    ],
)
def test_query_endpoint_rejects_invalid_payload_before_side_effects(
    monkeypatch,  # noqa: ANN001
    payload: dict[str, object],
) -> None:
    external_calls: list[object] = []

    async def fake_fetch_external_result(payload, settings) -> bool:  # noqa: ANN001
        external_calls.append(payload)
        return True

    pool = FakePool()
    app.state.db_pool = pool
    app.state.settings = Settings(
        database_url="postgresql://postgres:postgres@db:5432/test",
    )
    monkeypatch.setattr(routes, "fetch_external_result", fake_fetch_external_result)
    client = TestClient(app)

    response = client.post("/query", json=payload)

    assert response.status_code == 422
    assert external_calls == []
    assert pool.connection.executed_queries == []


@pytest.mark.parametrize(
    "payload",
    [
        {**VALID_PAYLOAD, "cadastral_number": "77:01:0004012"},
        {**VALID_PAYLOAD, "latitude": -90.000001},
        {**VALID_PAYLOAD, "latitude": 90.000001},
        {**VALID_PAYLOAD, "longitude": -180.000001},
        {**VALID_PAYLOAD, "longitude": 180.000001},
        {**VALID_PAYLOAD, "latitude": "55.7558"},
        {**VALID_PAYLOAD, "longitude": "37.6173"},
    ],
)
def test_external_service_result_rejects_invalid_payload(
    payload: dict[str, object],
) -> None:
    client = TestClient(external_app)

    response = client.post("/result", json=payload)

    assert response.status_code == 422
