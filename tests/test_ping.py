from fastapi.testclient import TestClient

from app.main import app


class FakeConnection:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def fetchval(self, query: str) -> int:
        self.queries.append(query)
        return 1


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


def test_ping_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/ping")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ping_db_returns_ok() -> None:
    pool = FakePool()
    app.state.db_pool = pool
    client = TestClient(app)

    response = client.get("/ping/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert pool.connection.queries == ["SELECT 1"]
