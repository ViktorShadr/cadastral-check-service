# Architecture

## Overview

Cadastral Check Service is an asynchronous FastAPI backend for checking cadastral
objects. The service accepts a cadastral number with geographic coordinates,
requests a separate external-service emulator, stores the request and the boolean
result in PostgreSQL, and exposes request history through authenticated API
endpoints.

The project is intentionally compact and layered:

- `app/main.py` assembles the FastAPI application and owns application lifecycle.
- `app/api/` contains HTTP route handlers and request dependencies.
- `app/core/` contains infrastructure-level configuration, database pool setup,
  password hashing, and JWT helpers.
- `app/services/` contains integration code for the external result provider.
- `app/schemas.py` defines Pydantic request and response contracts.
- `external_service/` contains a separate FastAPI application that emulates the
  external cadastral result provider.
- `migrations/` and `scripts/migrate.py` define and apply raw SQL migrations.

The application does not use an ORM. API handlers issue parameterized SQL through
`asyncpg` and validate all public request payloads with Pydantic models before any
external call or database write is performed.

## Request Flow

### Application Startup

1. Uvicorn imports `app.main:app`.
2. FastAPI runs the lifespan context manager from `app/main.py`.
3. `Settings()` loads runtime configuration from environment variables and `.env`.
4. `create_db_pool(settings)` creates a shared `asyncpg` connection pool.
5. `settings` and `db_pool` are stored in `app.state` and reused by dependencies,
   route handlers, and services.
6. On shutdown, `close_db_pool(pool)` closes the database pool.

### Authenticated Cadastral Check: `POST /query`

1. The client sends JSON with `cadastral_number`, `latitude`, and `longitude`, plus
   `Authorization: Bearer <access_token>`.
2. FastAPI validates the request body using `QueryRequest` from `app/schemas.py`:
   cadastral number must have four numeric colon-separated parts, latitude must be
   between `-90` and `90`, and longitude must be between `-180` and `180`.
3. `get_current_user` extracts the bearer token, verifies the JWT signature and
   expiration with `decode_access_token`, then loads the active user from `users`.
4. `request_external_result` calls `fetch_external_result` from
   `app/services/external_result.py`.
5. The service layer sends `POST /result` to `EXTERNAL_SERVICE_URL` using
   `httpx.AsyncClient` and the configured timeout.
6. The external-service emulator validates the same `QueryRequest` schema, waits
   briefly, and returns `{"result": true}` or `{"result": false}`.
7. The main service validates the provider response as `QueryResponse`.
8. The API handler inserts a new row into `request_history` with the current
   `user_id`, request payload, returned boolean result, and database timestamp.
9. The client receives `{"result": true}` or `{"result": false}`.

If the external service cannot be reached, returns an invalid response, or exceeds
the timeout, the main API maps the integration failure to `502` or `504` and does
not write request history.

### History Read: `GET /history`

1. The client sends `Authorization: Bearer <access_token>`.
2. `get_current_user` validates the token and loads the active user.
3. Optional query parameters are validated: `cadastral_number`, `limit`, and
   `offset`.
4. Regular users are scoped to `request_history.user_id = current_user.id`.
5. Admin users can call the same endpoint and see all history rows, but the public
   response model still omits `user_id`.
6. Rows are ordered by `created_at DESC` and returned as `HistoryItem` objects.

### Admin API And Panel

Administrative API endpoints under `/admin` use `get_current_admin_user`, which
requires a valid bearer token and `users.is_admin = true`.

The server-rendered admin panel under `/admin/panel` uses the same admin check but
can authenticate either by bearer token or by the `admin_panel_token` HttpOnly
cookie created by `POST /admin/panel/login`.

## Components

### API Layer

`app/api/routes.py` contains public service routes:

- `GET /ping` for process health.
- `GET /ping/db` for database connectivity.
- `POST /result` compatibility endpoint that proxies a required request body to
  the external result service and returns a raw JSON boolean.
- `POST /query` for authenticated cadastral checks and history persistence.
- `GET /history` for authenticated request history with optional cadastral number
  filtering and pagination.

`app/api/auth.py` contains authentication routes:

- `POST /auth/register` creates a user with a PBKDF2 password hash.
- `POST /auth/login` verifies credentials and returns a JWT access token.
- `GET /auth/me` returns the authenticated public user profile.

`app/api/admin.py` contains JSON admin endpoints and HTML admin panel routes:

- `GET /admin/users` lists users.
- `GET /admin/history` lists all history with optional filters.
- `GET /admin/history/{request_id}` returns one history record.
- `/admin/panel/*` renders a minimal Jinja2-based admin UI.

### Schema And Validation Layer

`app/schemas.py` centralizes API contracts and validators:

- `QueryRequest` and `QueryResponse` define cadastral check input/output.
- `RegisterRequest`, `LoginRequest`, and `Token` define auth contracts.
- `UserPublic` and `UserInDB` split API-safe user data from internal password
  hash data.
- `HistoryItem` and `AdminHistoryItem` define user and admin history responses.

Pydantic validators normalize email and cadastral number fields and reject invalid
coordinates before route handlers execute side effects.

### Service Integration Layer

`app/services/external_result.py` is the client for the external result provider.
It uses `httpx.AsyncClient`, sends `POST /result`, validates the response as
`QueryResponse`, and raises typed exceptions for timeout, availability, and
invalid response failures.

### Infrastructure Layer

`app/core/config.py` defines `Settings` loaded from environment variables and
`.env` through `pydantic-settings`.

`app/core/database.py` creates and closes the shared `asyncpg` pool.

`app/core/security.py` implements password hashing with PBKDF2-HMAC-SHA256 and
JWT creation/validation with HMAC SHA-256 (`HS256`).

### Database And Migrations

SQL migrations live in `migrations/`. `scripts/migrate.py` applies ordered `*.sql`
files, records applied files in `schema_migrations`, and is executed automatically
by the Docker image before the main Uvicorn process starts.

### External Result Emulator

`external_service/main.py` is a separate FastAPI application. It exposes
`POST /result`, accepts the same `QueryRequest` schema, waits `0.1` seconds, and
returns a random `QueryResponse` boolean. In Docker Compose it runs as a separate
service named `external-service` on container port `8001` and is reachable from
the host through `EXTERNAL_SERVICE_PORT` defaulting to `8002`.

## Used Technologies

- Python 3.12+
- FastAPI
- Uvicorn
- Pydantic and pydantic-settings
- PostgreSQL 16 in Docker Compose
- asyncpg
- httpx
- Jinja2 templates for the HTML admin panel
- Raw SQL migrations
- Docker and Docker Compose
- Poetry
- Pytest
- Black, isort, and flake8

## Project Structure

```text
.
├── app/
│   ├── api/
│   │   ├── admin.py          # Admin JSON API and HTML panel routes
│   │   ├── auth.py           # Registration, login, current-user routes
│   │   ├── dependencies.py   # Auth and settings dependencies
│   │   └── routes.py         # Health, result, query, and history routes
│   ├── core/
│   │   ├── config.py         # Environment-based settings
│   │   ├── database.py       # asyncpg pool lifecycle helpers
│   │   └── security.py       # Password hashing and JWT helpers
│   ├── services/
│   │   └── external_result.py # HTTP client for the external result provider
│   ├── templates/admin/      # Jinja2 templates for the admin panel
│   ├── main.py               # FastAPI app assembly and lifespan
│   └── schemas.py            # Pydantic schemas and validators
├── external_service/
│   └── main.py               # External result emulator FastAPI app
├── migrations/
│   ├── 0001_create_request_history.sql
│   └── 0002_create_users_and_link_history.sql
├── scripts/
│   └── migrate.py            # Raw SQL migration runner
├── tests/                    # Pytest test suite
├── Dockerfile                # Application image and startup command
├── docker-compose.yml        # App, external-service, and PostgreSQL services
├── pyproject.toml            # Dependencies and tool configuration
└── README.md
```

## Architecture Diagram

```text
+-------------------+         +--------------------------+
| HTTP Client       |         | Browser Admin Panel      |
| curl / frontend   |         | /admin/panel/*           |
+---------+---------+         +------------+-------------+
          |                                |
          | JSON + Bearer JWT              | HTML form / cookie / Bearer JWT
          v                                v
+--------------------------------------------------------+
| Main FastAPI Application: app.main                     |
|                                                        |
|  +-------------------+   +--------------------------+  |
|  | API Routers       |   | Dependencies             |  |
|  | routes/auth/admin |-->| auth, admin, settings    |  |
|  +---------+---------+   +------------+-------------+  |
|            |                          |                |
|            v                          v                |
|  +-------------------+   +--------------------------+  |
|  | Pydantic Schemas  |   | Security Helpers         |  |
|  | validation        |   | PBKDF2, JWT HS256        |  |
|  +---------+---------+   +------------+-------------+  |
|            |                          |                |
|            v                          v                |
|  +-------------------+       +----------------------+  |
|  | External Result   |       | asyncpg Pool         |  |
|  | Service Client    |       | app.state.db_pool    |  |
|  +---------+---------+       +----------+-----------+  |
+------------|----------------------------|--------------+
             |                            |
             | POST /result               | SQL
             v                            v
+-----------------------------+   +----------------------+
| External FastAPI Emulator   |   | PostgreSQL           |
| external_service.main       |   | users                |
| returns random boolean      |   | request_history      |
+-----------------------------+   | schema_migrations    |
                                  +----------------------+
```
