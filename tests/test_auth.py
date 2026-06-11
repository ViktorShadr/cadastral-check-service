from datetime import UTC, datetime

import asyncpg
from fastapi.testclient import TestClient

from app.api import routes
from app.core.config import Settings
from app.main import app

REGISTER_PAYLOAD = {"email": "User@Example.com", "password": "strong-password"}
LOGIN_PAYLOAD = {"email": "user@example.com", "password": "strong-password"}
QUERY_PAYLOAD = {
    "cadastral_number": "77:01:0004012:2054",
    "latitude": 55.7558,
    "longitude": 37.6173,
}


class FakeConnection:
    def __init__(self, pool: "FakePool") -> None:
        self.pool = pool

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.pool.fetchrow_calls.append((query, args))
        normalized_query = " ".join(query.lower().split())

        if "insert into users" in normalized_query:
            return self.pool.insert_user(args)

        if "from users" in normalized_query and "where email = $1" in normalized_query:
            return self.pool.users_by_email.get(args[0])

        if "from users" in normalized_query and "where id = $1" in normalized_query:
            return self.pool.users_by_id.get(args[0])

        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def execute(self, query: str, *args: object) -> str:
        self.pool.execute_calls.append((query, args))
        normalized_query = " ".join(query.lower().split())

        if "insert into request_history" in normalized_query:
            user_id, cadastral_number, latitude, longitude, result = args
            self.pool.history.append(
                {
                    "id": len(self.pool.history) + 1,
                    "user_id": user_id,
                    "cadastral_number": cadastral_number,
                    "latitude": latitude,
                    "longitude": longitude,
                    "result": result,
                    "created_at": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
                }
            )
            return "INSERT 0 1"

        raise AssertionError(f"Unexpected execute query: {query}")

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.pool.fetch_calls.append((query, args))
        rows = sorted(
            self.pool.history,
            key=lambda row: row["created_at"],
            reverse=True,
        )

        if "user_id = $1" in query:
            rows = [row for row in rows if row["user_id"] == args[0]]

        if "cadastral_number =" in query:
            cadastral_number = args[1] if "user_id = $1" in query else args[0]
            rows = [row for row in rows if row["cadastral_number"] == cadastral_number]

        limit = int(args[-2])
        offset = int(args[-1])
        return [
            self.pool.public_history_row(row) for row in rows[offset : offset + limit]
        ]


class FakeAcquireContext:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        return None


class FakePool:
    def __init__(self) -> None:
        self.connection = FakeConnection(self)
        self.users_by_email: dict[object, dict[str, object]] = {}
        self.users_by_id: dict[object, dict[str, object]] = {}
        self.history: list[dict[str, object]] = []
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.next_user_id = 1

    def acquire(self) -> FakeAcquireContext:
        return FakeAcquireContext(self.connection)

    def insert_user(self, args: tuple[object, ...]) -> dict[str, object]:
        email, hashed_password = args
        if email in self.users_by_email:
            raise asyncpg.UniqueViolationError("duplicate email")

        user = {
            "id": self.next_user_id,
            "email": email,
            "hashed_password": hashed_password,
            "is_active": True,
            "is_admin": False,
            "created_at": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        }
        self.next_user_id += 1
        self.users_by_email[email] = user
        self.users_by_id[user["id"]] = user
        return {key: value for key, value in user.items() if key != "hashed_password"}

    def public_history_row(self, row: dict[str, object]) -> dict[str, object]:
        return {
            "id": row["id"],
            "cadastral_number": row["cadastral_number"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "result": row["result"],
            "created_at": row["created_at"],
        }


def configure_app(pool: FakePool) -> None:
    app.state.db_pool = pool
    app.state.settings = Settings(
        database_url="postgresql://postgres:postgres@db:5432/test",
        jwt_secret_key="test-secret",
        access_token_expire_minutes=30,
    )


def register_and_login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201

    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_successful_registration() -> None:
    pool = FakePool()
    configure_app(pool)
    client = TestClient(app)

    response = client.post("/auth/register", json=REGISTER_PAYLOAD)

    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "email": "user@example.com",
        "is_active": True,
        "is_admin": False,
        "created_at": "2026-01-01T12:00:00Z",
    }
    stored_user = pool.users_by_email["user@example.com"]
    assert stored_user["hashed_password"] != REGISTER_PAYLOAD["password"]
    assert str(stored_user["hashed_password"]).startswith("pbkdf2_sha256$")


def test_registration_rejects_duplicate_email() -> None:
    pool = FakePool()
    configure_app(pool)
    client = TestClient(app)

    first_response = client.post("/auth/register", json=REGISTER_PAYLOAD)
    second_response = client.post("/auth/register", json=REGISTER_PAYLOAD)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {"detail": "Email is already registered."}


def test_successful_login_returns_access_token() -> None:
    pool = FakePool()
    configure_app(pool)
    client = TestClient(app)
    client.post("/auth/register", json=REGISTER_PAYLOAD)

    response = client.post("/auth/login", json=LOGIN_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert len(response.json()["access_token"].split(".")) == 3


def test_protected_query_accepts_valid_token(monkeypatch) -> None:  # noqa: ANN001
    async def fake_fetch_external_result(payload, settings) -> bool:  # noqa: ANN001
        assert payload.cadastral_number == "77:01:0004012:2054"
        return True

    pool = FakePool()
    configure_app(pool)
    monkeypatch.setattr(routes, "fetch_external_result", fake_fetch_external_result)
    client = TestClient(app)
    token = register_and_login(client, "user@example.com", "strong-password")

    response = client.post(
        "/query",
        json=QUERY_PAYLOAD,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"result": True}
    assert len(pool.execute_calls) == 1
    query, args = pool.execute_calls[0]
    assert "INSERT INTO request_history" in query
    assert args == (1, "77:01:0004012:2054", 55.7558, 37.6173, True)


def test_protected_endpoints_reject_request_without_token(
    monkeypatch,
) -> None:  # noqa: ANN001
    external_calls: list[object] = []

    async def fake_fetch_external_result(payload, settings) -> bool:  # noqa: ANN001
        external_calls.append(payload)
        return True

    pool = FakePool()
    configure_app(pool)
    monkeypatch.setattr(routes, "fetch_external_result", fake_fetch_external_result)
    client = TestClient(app)

    query_response = client.post("/query", json=QUERY_PAYLOAD)
    history_response = client.get("/history")

    assert query_response.status_code == 401
    assert history_response.status_code == 401
    assert external_calls == []
    assert pool.execute_calls == []
    assert pool.fetch_calls == []


def test_history_returns_only_current_user_data() -> None:
    pool = FakePool()
    configure_app(pool)
    client = TestClient(app)
    first_token = register_and_login(client, "first@example.com", "strong-password")
    register_and_login(client, "second@example.com", "strong-password")
    pool.history = [
        {
            "id": 1,
            "user_id": 1,
            "cadastral_number": "77:01:0004012:2054",
            "latitude": 55.7558,
            "longitude": 37.6173,
            "result": True,
            "created_at": datetime(2026, 1, 2, 12, 0, tzinfo=UTC),
        },
        {
            "id": 2,
            "user_id": 2,
            "cadastral_number": "77:01:0004012:2055",
            "latitude": 55.7559,
            "longitude": 37.6174,
            "result": False,
            "created_at": datetime(2026, 1, 3, 12, 0, tzinfo=UTC),
        },
    ]

    response = client.get(
        "/history", headers={"Authorization": f"Bearer {first_token}"}
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [1]
    query, args = pool.fetch_calls[-1]
    assert "WHERE user_id = $1" in query
    assert args == (1, 100, 0)
