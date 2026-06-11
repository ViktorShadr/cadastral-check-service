from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.config import Settings
from app.core.security import hash_password
from app.main import app
from app.schemas import UserInDB


class FakeConnection:
    def __init__(self, pool: "FakePool") -> None:
        self.pool = pool
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.fetch_calls.append((query, args))
        normalized_query = " ".join(query.lower().split())

        if "from users" in normalized_query:
            rows = sorted(
                self.pool.users,
                key=lambda row: (row["created_at"], row["id"]),
                reverse=True,
            )
            limit = int(args[-2])
            offset = int(args[-1])
            return rows[offset : offset + limit]

        if "from request_history" in normalized_query:
            rows = sorted(
                self.pool.history,
                key=lambda row: (row["created_at"], row["id"]),
                reverse=True,
            )

            if "left join users" in normalized_query:
                rows = [self.pool.add_user_email(row) for row in rows]

            filter_arg_index = 0

            if "cadastral_number = $" in normalized_query:
                cadastral_number = args[filter_arg_index]
                filter_arg_index += 1
                rows = [
                    row for row in rows if row["cadastral_number"] == cadastral_number
                ]

            if "user_id = $" in normalized_query:
                user_id = args[filter_arg_index]
                filter_arg_index += 1
                rows = [row for row in rows if row["user_id"] == user_id]

            if "result = $" in normalized_query:
                result = args[filter_arg_index]
                rows = [row for row in rows if row["result"] == result]

            limit = int(args[-2])
            offset = int(args[-1])
            return rows[offset : offset + limit]

        raise AssertionError(f"Unexpected fetch query: {query}")

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.fetchrow_calls.append((query, args))
        normalized_query = " ".join(query.lower().split())

        if "from request_history" in normalized_query and (
            "where id = $1" in normalized_query
            or "where rh.id = $1" in normalized_query
        ):
            request_id = args[0]
            row = next(
                (row for row in self.pool.history if row["id"] == request_id),
                None,
            )
            if row is not None and "left join users" in normalized_query:
                return self.pool.add_user_email(row)

            return row

        if "from users" in normalized_query and "where email = $1" in normalized_query:
            email = args[0]
            return next(
                (user for user in self.pool.users if user["email"] == email), None
            )

        if "from users" in normalized_query and "where id = $1" in normalized_query:
            user_id = args[0]
            return next(
                (user for user in self.pool.users if user["id"] == user_id), None
            )

        raise AssertionError(f"Unexpected fetchrow query: {query}")


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
        self.users = [
            {
                "id": 1,
                "email": "user@example.com",
                "hashed_password": hash_password("regular-password"),
                "is_active": True,
                "is_admin": False,
                "created_at": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            },
            {
                "id": 2,
                "email": "admin@example.com",
                "hashed_password": hash_password("admin-password"),
                "is_active": True,
                "is_admin": True,
                "created_at": datetime(2026, 1, 2, 12, 0, tzinfo=UTC),
            },
        ]
        self.history = [
            {
                "id": 1,
                "user_id": 1,
                "cadastral_number": "77:01:0004012:2054",
                "latitude": 55.7558,
                "longitude": 37.6173,
                "result": True,
                "created_at": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            },
            {
                "id": 2,
                "user_id": 2,
                "cadastral_number": "77:01:0004012:2055",
                "latitude": 55.7559,
                "longitude": 37.6174,
                "result": False,
                "created_at": datetime(2026, 1, 2, 12, 0, tzinfo=UTC),
            },
        ]

    def acquire(self) -> FakeAcquireContext:
        return FakeAcquireContext(self.connection)

    def add_user_email(self, row: dict[str, object]) -> dict[str, object]:
        user = next(
            (user for user in self.users if user["id"] == row["user_id"]),
            None,
        )
        return {
            **row,
            "user_email": user["email"] if user is not None else None,
        }


def override_current_user(is_admin: bool) -> UserInDB:
    user = UserInDB(
        id=2 if is_admin else 1,
        email="admin@example.com" if is_admin else "user@example.com",
        hashed_password="not-used-in-route-tests",
        is_active=True,
        is_admin=is_admin,
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )

    async def dependency_override() -> UserInDB:
        return user

    app.dependency_overrides[get_current_user] = dependency_override
    return user


def test_admin_lists_users() -> None:
    pool = FakePool()
    app.state.db_pool = pool
    override_current_user(is_admin=True)
    client = TestClient(app)

    response = client.get("/admin/users")

    assert response.status_code == 200
    assert [item["email"] for item in response.json()] == [
        "admin@example.com",
        "user@example.com",
    ]
    query, args = pool.connection.fetch_calls[0]
    assert "FROM users" in query
    assert "ORDER BY created_at DESC, id DESC" in query
    assert args == (100, 0)


def test_admin_sees_all_history() -> None:
    pool = FakePool()
    app.state.db_pool = pool
    override_current_user(is_admin=True)
    client = TestClient(app)

    response = client.get("/admin/history")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [2, 1]
    assert [item["user_id"] for item in response.json()] == [2, 1]
    query, args = pool.connection.fetch_calls[0]
    assert "FROM request_history" in query
    assert "WHERE" not in query
    assert "ORDER BY created_at DESC, id DESC" in query
    assert args == (100, 0)


def test_admin_can_open_history_request() -> None:
    pool = FakePool()
    app.state.db_pool = pool
    override_current_user(is_admin=True)
    client = TestClient(app)

    response = client.get("/admin/history/2")

    assert response.status_code == 200
    assert response.json()["id"] == 2
    assert response.json()["user_id"] == 2
    query, args = pool.connection.fetchrow_calls[0]
    assert "FROM request_history" in query
    assert "WHERE id = $1" in query
    assert args == (2,)


@pytest.mark.parametrize(
    "path",
    [
        "/admin/users",
        "/admin/history",
        "/admin/history/1",
    ],
)
def test_regular_user_has_no_admin_access(path: str) -> None:
    pool = FakePool()
    app.state.db_pool = pool
    override_current_user(is_admin=False)
    client = TestClient(app)

    response = client.get(path)

    assert response.status_code == 403
    assert response.json() == {"detail": "Admin access required."}
    assert pool.connection.fetch_calls == []
    assert pool.connection.fetchrow_calls == []


@pytest.mark.parametrize(
    "path",
    [
        "/admin/users",
        "/admin/history",
        "/admin/history/1",
    ],
)
def test_unauthorized_user_has_no_admin_access(path: str) -> None:
    pool = FakePool()
    app.state.db_pool = pool
    client = TestClient(app)

    response = client.get(path)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}
    assert pool.connection.fetch_calls == []
    assert pool.connection.fetchrow_calls == []


def test_admin_history_filters_and_pagination_work() -> None:
    pool = FakePool()
    pool.history = [
        {
            "id": 1,
            "user_id": 2,
            "cadastral_number": "77:01:0004012:2054",
            "latitude": 55.7558,
            "longitude": 37.6173,
            "result": False,
            "created_at": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        },
        {
            "id": 2,
            "user_id": 2,
            "cadastral_number": "77:01:0004012:2054",
            "latitude": 55.7559,
            "longitude": 37.6174,
            "result": False,
            "created_at": datetime(2026, 1, 2, 12, 0, tzinfo=UTC),
        },
        {
            "id": 3,
            "user_id": 2,
            "cadastral_number": "77:01:0004012:2054",
            "latitude": 55.7560,
            "longitude": 37.6175,
            "result": False,
            "created_at": datetime(2026, 1, 3, 12, 0, tzinfo=UTC),
        },
        {
            "id": 4,
            "user_id": 1,
            "cadastral_number": "77:01:0004012:2054",
            "latitude": 55.7561,
            "longitude": 37.6176,
            "result": False,
            "created_at": datetime(2026, 1, 4, 12, 0, tzinfo=UTC),
        },
        {
            "id": 5,
            "user_id": 2,
            "cadastral_number": "77:01:0004012:2056",
            "latitude": 55.7562,
            "longitude": 37.6177,
            "result": False,
            "created_at": datetime(2026, 1, 5, 12, 0, tzinfo=UTC),
        },
        {
            "id": 6,
            "user_id": 2,
            "cadastral_number": "77:01:0004012:2054",
            "latitude": 55.7563,
            "longitude": 37.6178,
            "result": True,
            "created_at": datetime(2026, 1, 6, 12, 0, tzinfo=UTC),
        },
    ]
    app.state.db_pool = pool
    override_current_user(is_admin=True)
    client = TestClient(app)

    response = client.get(
        "/admin/history",
        params={
            "cadastral_number": "77:01:0004012:2054",
            "user_id": 2,
            "result": "false",
            "limit": 1,
            "offset": 1,
        },
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [2]
    query, args = pool.connection.fetch_calls[0]
    assert "WHERE cadastral_number = $1 AND user_id = $2 AND result = $3" in query
    assert "LIMIT $4 OFFSET $5" in query
    assert args == ("77:01:0004012:2054", 2, False, 1, 1)


@pytest.mark.parametrize(
    "path",
    [
        "/admin/panel",
        "/admin/panel/users",
        "/admin/panel/history",
        "/admin/panel/history/1",
    ],
)
def test_admin_can_access_admin_panel_pages(path: str) -> None:
    pool = FakePool()
    app.state.db_pool = pool
    override_current_user(is_admin=True)
    client = TestClient(app)

    response = client.get(path)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Cadastral Admin" in response.text


@pytest.mark.parametrize(
    "path",
    [
        "/admin/panel",
        "/admin/panel/users",
        "/admin/panel/history",
        "/admin/panel/history/1",
    ],
)
def test_regular_user_has_no_admin_panel_access(path: str) -> None:
    pool = FakePool()
    app.state.db_pool = pool
    override_current_user(is_admin=False)
    client = TestClient(app)

    response = client.get(path)

    assert response.status_code == 403
    assert response.json() == {"detail": "Admin access required."}
    assert pool.connection.fetch_calls == []
    assert pool.connection.fetchrow_calls == []


@pytest.mark.parametrize(
    "path",
    [
        "/admin/panel",
        "/admin/panel/users",
        "/admin/panel/history",
        "/admin/panel/history/1",
    ],
)
def test_unauthorized_user_has_no_admin_panel_access(path: str) -> None:
    pool = FakePool()
    app.state.db_pool = pool
    client = TestClient(app)

    response = client.get(path)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}
    assert pool.connection.fetch_calls == []
    assert pool.connection.fetchrow_calls == []


def test_admin_panel_history_contains_created_request_data() -> None:
    pool = FakePool()
    app.state.db_pool = pool
    override_current_user(is_admin=True)
    client = TestClient(app)

    response = client.get("/admin/panel/history")

    assert response.status_code == 200
    assert "77:01:0004012:2055" in response.text
    assert "admin@example.com" in response.text
    assert "55.7559" in response.text
    assert "37.6174" in response.text
    assert "False" in response.text


def test_admin_panel_users_contains_user_email() -> None:
    pool = FakePool()
    app.state.db_pool = pool
    override_current_user(is_admin=True)
    client = TestClient(app)

    response = client.get("/admin/panel/users")

    assert response.status_code == 200
    assert "admin@example.com" in response.text
    assert "user@example.com" in response.text


def test_admin_panel_login_form_is_available() -> None:
    client = TestClient(app)

    response = client.get("/admin/panel/login")

    assert response.status_code == 200
    assert "Admin Login" in response.text
    assert 'name="email"' in response.text
    assert 'name="password"' in response.text


def test_admin_can_login_to_panel_with_cookie_session() -> None:
    pool = FakePool()
    app.state.db_pool = pool
    app.state.settings = Settings(database_url="postgresql://test/test")
    client = TestClient(app)

    response = client.post(
        "/admin/panel/login",
        data={
            "email": "admin@example.com",
            "password": "admin-password",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/panel"
    assert "admin_panel_token" in response.headers["set-cookie"]

    panel_response = client.get("/admin/panel/users")

    assert panel_response.status_code == 200
    assert "admin@example.com" in panel_response.text


def test_regular_user_cannot_login_to_admin_panel() -> None:
    pool = FakePool()
    app.state.db_pool = pool
    app.state.settings = Settings(database_url="postgresql://test/test")
    client = TestClient(app)

    response = client.post(
        "/admin/panel/login",
        data={
            "email": "user@example.com",
            "password": "regular-password",
        },
    )

    assert response.status_code == 403
    assert "Admin access required." in response.text


def test_invalid_admin_panel_login_is_rejected() -> None:
    pool = FakePool()
    app.state.db_pool = pool
    client = TestClient(app)

    response = client.post(
        "/admin/panel/login",
        data={
            "email": "admin@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert "Invalid email or password." in response.text
