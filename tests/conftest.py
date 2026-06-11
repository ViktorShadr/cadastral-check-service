from datetime import UTC, datetime

import pytest

from app.api.dependencies import get_current_user
from app.main import app
from app.schemas import UserInDB


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> None:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_user() -> UserInDB:
    user = UserInDB(
        id=123,
        email="user@example.com",
        hashed_password="not-used-in-route-tests",
        is_active=True,
        is_admin=False,
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )

    async def override_current_user() -> UserInDB:
        return user

    app.dependency_overrides[get_current_user] = override_current_user
    return user
