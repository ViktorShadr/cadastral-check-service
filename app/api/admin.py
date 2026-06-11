"""Administrative API and HTML panel endpoints."""

import inspect
from pathlib import Path as FilePath
from typing import Annotated
from urllib.parse import parse_qs

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.templating import Jinja2Templates

from app.api.dependencies import (
    auth_error,
    bearer_scheme,
    get_current_admin_user,
    get_current_user,
    get_settings,
)
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    verify_password,
)
from app.schemas import AdminHistoryItem, OptionalCadastralNumber, UserInDB, UserPublic

router = APIRouter(prefix="/admin", tags=["admin"])
DEFAULT_ADMIN_LIMIT = 100
MAX_ADMIN_LIMIT = 500
ADMIN_PANEL_COOKIE_NAME = "admin_panel_token"
templates = Jinja2Templates(
    directory=str(FilePath(__file__).resolve().parents[1] / "templates")
)


async def get_current_panel_admin_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ] = None,
) -> UserInDB:
    """Resolve an administrator for the HTML panel or bearer-based admin calls.

    Args:
        request: Incoming request with cookies, overrides, and app state.
        credentials: Optional bearer credentials supplied by API clients.

    Returns:
        Authenticated administrator user.

    Raises:
        HTTPException: If the user is unauthenticated or lacks admin access.
    """
    current_user = await get_panel_user(request, credentials)
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )

    return current_user


async def get_panel_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> UserInDB:
    """Resolve a panel user from dependency overrides, cookie, or bearer token.

    Args:
        request: Incoming request with cookies and app state.
        credentials: Optional bearer credentials that override the panel cookie.

    Returns:
        Authenticated active user.

    Raises:
        HTTPException: If no valid user can be resolved.
    """
    override = request.app.dependency_overrides.get(get_current_user)
    if override is not None:
        current_user = override()
        if inspect.isawaitable(current_user):
            current_user = await current_user

        return current_user

    token = request.cookies.get(ADMIN_PANEL_COOKIE_NAME)
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials

    if token is None:
        raise auth_error()

    return await get_user_by_access_token(request, token)


async def get_user_by_access_token(request: Request, token: str) -> UserInDB:
    """Load an active user referenced by an access token.

    Args:
        request: Incoming request with settings and database pool.
        token: Access token from an admin panel cookie or bearer header.

    Returns:
        Active user loaded from the database.

    Raises:
        HTTPException: If the token is invalid, expired, or references an
            inactive or missing user.
    """
    settings = get_settings(request)
    try:
        user_id = decode_access_token(token, settings)
    except InvalidTokenError as exc:
        raise auth_error("Invalid or expired token.") from exc

    pool: asyncpg.Pool = request.app.state.db_pool
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                id,
                email,
                hashed_password,
                is_active,
                is_admin,
                created_at
            FROM users
            WHERE id = $1
            """,
            user_id,
        )

    if row is None:
        raise auth_error("Invalid or expired token.")

    user = UserInDB(**dict(row))
    if not user.is_active:
        raise auth_error("Inactive user.")

    return user


async def get_user_by_email(request: Request, email: str) -> UserInDB | None:
    """Load a user by email for admin panel login.

    Args:
        request: Incoming request with access to the database pool.
        email: Normalized email submitted by the admin login form.

    Returns:
        Internal user record when found, otherwise None.
    """
    pool: asyncpg.Pool = request.app.state.db_pool

    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                id,
                email,
                hashed_password,
                is_active,
                is_admin,
                created_at
            FROM users
            WHERE email = $1
            """,
            email,
        )

    if row is None:
        return None

    return UserInDB(**dict(row))


def render_login(
    request: Request,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
):
    """Render the admin login page with an optional validation error.

    Args:
        request: Incoming request used by the template renderer.
        error: Optional message shown to the user.
        status_code: HTTP status code for the rendered response.

    Returns:
        Template response for the admin login page.
    """
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {
            "title": "Admin Login",
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/users", response_model=list[UserPublic])
async def users(
    request: Request,
    _current_admin_user: Annotated[UserInDB, Depends(get_current_admin_user)],
    limit: Annotated[int, Query(ge=1, le=MAX_ADMIN_LIMIT)] = DEFAULT_ADMIN_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[UserPublic]:
    """Return a paginated list of users for administrators.

    Args:
        request: Incoming request with access to the database pool.
        _current_admin_user: Admin dependency enforcing access control.
        limit: Maximum number of users to return.
        offset: Number of users to skip.

    Returns:
        List of public user records ordered by newest first.

    Raises:
        HTTPException: If the caller is not authenticated as an administrator.
        asyncpg.PostgresError: If the users query fails.
    """
    pool: asyncpg.Pool = request.app.state.db_pool

    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                id,
                email,
                is_active,
                is_admin,
                created_at
            FROM users
            ORDER BY created_at DESC, id DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )

    return [UserPublic(**dict(row)) for row in rows]


@router.get("/history", response_model=list[AdminHistoryItem])
async def history(
    request: Request,
    _current_admin_user: Annotated[UserInDB, Depends(get_current_admin_user)],
    cadastral_number: Annotated[
        OptionalCadastralNumber,
        Query(),
    ] = None,
    user_id: Annotated[int | None, Query(ge=1)] = None,
    result: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_ADMIN_LIMIT)] = DEFAULT_ADMIN_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminHistoryItem]:
    """Return filtered cadastral check history across all users.

    Args:
        request: Incoming request with access to the database pool.
        _current_admin_user: Admin dependency enforcing access control.
        cadastral_number: Optional cadastral number filter.
        user_id: Optional owner user identifier filter.
        result: Optional boolean result filter.
        limit: Maximum number of history entries to return.
        offset: Number of matching entries to skip.

    Returns:
        List of administrative history entries ordered by newest first.

    Raises:
        HTTPException: If the caller is not authenticated as an administrator.
        asyncpg.PostgresError: If the history query fails.
    """
    pool: asyncpg.Pool = request.app.state.db_pool
    query_text = """
        SELECT
            id,
            user_id,
            cadastral_number,
            latitude,
            longitude,
            result,
            created_at
        FROM request_history
    """
    query_args: list[object] = []
    where_clauses: list[str] = []

    if cadastral_number is not None:
        query_args.append(cadastral_number)
        where_clauses.append(f"cadastral_number = ${len(query_args)}")

    if user_id is not None:
        query_args.append(user_id)
        where_clauses.append(f"user_id = ${len(query_args)}")

    if result is not None:
        query_args.append(result)
        where_clauses.append(f"result = ${len(query_args)}")

    if where_clauses:
        query_text += " WHERE " + " AND ".join(where_clauses)

    limit_placeholder = len(query_args) + 1
    offset_placeholder = len(query_args) + 2
    query_text += (
        f" ORDER BY created_at DESC, id DESC LIMIT ${limit_placeholder}"
        f" OFFSET ${offset_placeholder}"
    )
    query_args.extend([limit, offset])

    async with pool.acquire() as connection:
        rows = await connection.fetch(query_text, *query_args)

    return [AdminHistoryItem(**dict(row)) for row in rows]


@router.get("/history/{request_id}", response_model=AdminHistoryItem)
async def history_item(
    request_id: Annotated[int, Path(ge=1)],
    request: Request,
    _current_admin_user: Annotated[UserInDB, Depends(get_current_admin_user)],
) -> AdminHistoryItem:
    """Return one history entry by identifier for administrators.

    Args:
        request_id: Identifier of the saved history request.
        request: Incoming request with access to the database pool.
        _current_admin_user: Admin dependency enforcing access control.

    Returns:
        Administrative history entry for the requested identifier.

    Raises:
        HTTPException: If the caller is not an administrator or the entry does
            not exist.
        asyncpg.PostgresError: If the lookup query fails.
    """
    pool: asyncpg.Pool = request.app.state.db_pool

    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                id,
                user_id,
                cadastral_number,
                latitude,
                longitude,
                result,
                created_at
            FROM request_history
            WHERE id = $1
            """,
            request_id,
        )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="History request not found.",
        )

    return AdminHistoryItem(**dict(row))


@router.get("/panel/login")
async def admin_panel_login(request: Request):
    """Render the admin panel login form.

    Args:
        request: Incoming request used by the template renderer.

    Returns:
        Template response containing the login form.
    """
    return render_login(request)


@router.post("/panel/login")
async def admin_panel_login_submit(request: Request):
    """Authenticate an administrator from the HTML login form.

    Args:
        request: Incoming request containing form-encoded credentials.

    Returns:
        Redirect response with an auth cookie on success, or the login template
        with an error message on failure.

    Raises:
        asyncpg.PostgresError: If user lookup fails.
    """
    body = (await request.body()).decode("utf-8")
    form = parse_qs(body, keep_blank_values=True)
    email = form.get("email", [""])[0].strip().lower()
    password = form.get("password", [""])[0]

    if not email or not password:
        return render_login(
            request,
            "Email and password are required.",
            status.HTTP_400_BAD_REQUEST,
        )

    user = await get_user_by_email(request, email)
    if (
        user is None
        or not user.is_active
        or not verify_password(
            password,
            user.hashed_password,
        )
    ):
        return render_login(
            request,
            "Invalid email or password.",
            status.HTTP_401_UNAUTHORIZED,
        )

    if not user.is_admin:
        return render_login(
            request,
            "Admin access required.",
            status.HTTP_403_FORBIDDEN,
        )

    settings = get_settings(request)
    response = RedirectResponse("/admin/panel", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        ADMIN_PANEL_COOKIE_NAME,
        create_access_token(user.id, settings),
        httponly=True,
        max_age=settings.access_token_expire_minutes * 60,
        path="/admin/panel",
        samesite="lax",
        secure=settings.cookie_secure,
    )

    return response


@router.post("/panel/logout")
async def admin_panel_logout():
    """Clear the admin panel authentication cookie.

    Args:
        None

    Returns:
        Redirect response to the admin login page.
    """
    response = RedirectResponse(
        "/admin/panel/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.delete_cookie(ADMIN_PANEL_COOKIE_NAME, path="/admin/panel")
    return response


@router.get("/panel")
async def admin_panel(
    request: Request,
    current_admin_user: Annotated[UserInDB, Depends(get_current_panel_admin_user)],
):
    """Render the admin panel landing page.

    Args:
        request: Incoming request used by the template renderer.
        current_admin_user: Authenticated administrator for panel context.

    Returns:
        Template response for the admin panel landing page.

    Raises:
        HTTPException: If the caller is not authenticated as an administrator.
    """
    return templates.TemplateResponse(
        request,
        "admin/panel.html",
        {
            "title": "Admin Panel",
            "current_admin_user": current_admin_user,
        },
    )


@router.get("/panel/users")
async def admin_panel_users(
    request: Request,
    current_admin_user: Annotated[UserInDB, Depends(get_current_panel_admin_user)],
    limit: Annotated[int, Query(ge=1, le=MAX_ADMIN_LIMIT)] = DEFAULT_ADMIN_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Render the admin panel users page.

    Args:
        request: Incoming request with access to the database pool.
        current_admin_user: Authenticated administrator for panel context.
        limit: Maximum number of users to render.
        offset: Number of users to skip.

    Returns:
        Template response containing user rows.

    Raises:
        HTTPException: If the caller is not authenticated as an administrator.
        asyncpg.PostgresError: If the users query fails.
    """
    pool: asyncpg.Pool = request.app.state.db_pool

    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                id,
                email,
                is_active,
                is_admin,
                created_at
            FROM users
            ORDER BY created_at DESC, id DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )

    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "title": "Admin Users",
            "current_admin_user": current_admin_user,
            "users": [dict(row) for row in rows],
        },
    )


@router.get("/panel/history")
async def admin_panel_history(
    request: Request,
    current_admin_user: Annotated[UserInDB, Depends(get_current_panel_admin_user)],
    limit: Annotated[int, Query(ge=1, le=MAX_ADMIN_LIMIT)] = DEFAULT_ADMIN_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Render the admin panel history list.

    Args:
        request: Incoming request with access to the database pool.
        current_admin_user: Authenticated administrator for panel context.
        limit: Maximum number of history rows to render.
        offset: Number of history rows to skip.

    Returns:
        Template response containing history rows with optional user emails.

    Raises:
        HTTPException: If the caller is not authenticated as an administrator.
        asyncpg.PostgresError: If the history query fails.
    """
    pool: asyncpg.Pool = request.app.state.db_pool

    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                rh.id,
                rh.user_id,
                u.email AS user_email,
                rh.cadastral_number,
                rh.latitude,
                rh.longitude,
                rh.result,
                rh.created_at
            FROM request_history rh
            LEFT JOIN users u ON u.id = rh.user_id
            ORDER BY rh.created_at DESC, rh.id DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )

    return templates.TemplateResponse(
        request,
        "admin/history.html",
        {
            "title": "Admin History",
            "current_admin_user": current_admin_user,
            "history_items": [dict(row) for row in rows],
        },
    )


@router.get("/panel/history/{request_id}")
async def admin_panel_history_item(
    request_id: Annotated[int, Path(ge=1)],
    request: Request,
    current_admin_user: Annotated[UserInDB, Depends(get_current_panel_admin_user)],
):
    """Render a single admin panel history entry.

    Args:
        request_id: Identifier of the saved history request.
        request: Incoming request with access to the database pool.
        current_admin_user: Authenticated administrator for panel context.

    Returns:
        Template response containing one history item.

    Raises:
        HTTPException: If the caller is not an administrator or the entry does
            not exist.
        asyncpg.PostgresError: If the lookup query fails.
    """
    pool: asyncpg.Pool = request.app.state.db_pool

    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                rh.id,
                rh.user_id,
                u.email AS user_email,
                rh.cadastral_number,
                rh.latitude,
                rh.longitude,
                rh.result,
                rh.created_at
            FROM request_history rh
            LEFT JOIN users u ON u.id = rh.user_id
            WHERE rh.id = $1
            """,
            request_id,
        )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="History request not found.",
        )

    return templates.TemplateResponse(
        request,
        "admin/history_item.html",
        {
            "title": f"History Request #{request_id}",
            "current_admin_user": current_admin_user,
            "history_item": dict(row),
        },
    )
