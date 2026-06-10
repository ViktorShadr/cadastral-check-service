from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app


class FakeConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.fetch_calls.append((query, args))
        return self.rows


class FakeAcquireContext:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        return None


class FakePool:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.connection = FakeConnection(rows)

    def acquire(self) -> FakeAcquireContext:
        return FakeAcquireContext(self.connection)


def test_history_returns_request_history_sorted_by_created_at() -> None:
    rows = [
        {
            "id": 2,
            "cadastral_number": "77:01:0004012:2055",
            "latitude": 55.7559,
            "longitude": 37.6174,
            "result": False,
            "created_at": datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc),
        },
        {
            "id": 1,
            "cadastral_number": "77:01:0004012:2054",
            "latitude": 55.7558,
            "longitude": 37.6173,
            "result": True,
            "created_at": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        },
    ]
    pool = FakePool(rows)
    app.state.db_pool = pool
    client = TestClient(app)

    response = client.get("/history")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 2,
            "cadastral_number": "77:01:0004012:2055",
            "latitude": 55.7559,
            "longitude": 37.6174,
            "result": False,
            "created_at": "2026-01-02T12:00:00Z",
        },
        {
            "id": 1,
            "cadastral_number": "77:01:0004012:2054",
            "latitude": 55.7558,
            "longitude": 37.6173,
            "result": True,
            "created_at": "2026-01-01T12:00:00Z",
        },
    ]

    query, args = pool.connection.fetch_calls[0]
    assert "FROM request_history" in query
    assert "ORDER BY created_at DESC" in query
    assert "LIMIT $1 OFFSET $2" in query
    assert "WHERE cadastral_number" not in query
    assert args == (100, 0)


def test_history_filters_by_cadastral_number() -> None:
    rows = [
        {
            "id": 1,
            "cadastral_number": "77:01:0004012:2054",
            "latitude": 55.7558,
            "longitude": 37.6173,
            "result": True,
            "created_at": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        }
    ]
    pool = FakePool(rows)
    app.state.db_pool = pool
    client = TestClient(app)

    response = client.get(
        "/history",
        params={"cadastral_number": "77:01:0004012:2054"},
    )

    assert response.status_code == 200
    assert response.json()[0]["cadastral_number"] == "77:01:0004012:2054"

    query, args = pool.connection.fetch_calls[0]
    assert "WHERE cadastral_number = $1" in query
    assert "ORDER BY created_at DESC" in query
    assert "LIMIT $2 OFFSET $3" in query
    assert args == ("77:01:0004012:2054", 100, 0)


def test_history_applies_limit_and_offset_to_sql() -> None:
    pool = FakePool([])
    app.state.db_pool = pool
    client = TestClient(app)

    response = client.get("/history", params={"limit": 25, "offset": 50})

    assert response.status_code == 200
    assert response.json() == []

    query, args = pool.connection.fetch_calls[0]
    assert "ORDER BY created_at DESC" in query
    assert "LIMIT $1 OFFSET $2" in query
    assert args == (25, 50)


def test_history_rejects_invalid_limit() -> None:
    pool = FakePool([])
    app.state.db_pool = pool
    client = TestClient(app)

    response = client.get("/history", params={"limit": 0})

    assert response.status_code == 422
    assert pool.connection.fetch_calls == []
