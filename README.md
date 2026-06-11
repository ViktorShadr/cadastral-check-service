# Cadastral Check Service

Backend service for cadastral checks. The main service accepts a cadastral
number, latitude, and longitude, requests a separate external-service emulator,
stores the request and boolean result in PostgreSQL, and exposes request history
through an API.

## Stack

- Python 3.12+
- FastAPI with async routes
- PostgreSQL
- asyncpg
- Pydantic and pydantic-settings
- Raw SQL migrations
- Docker and Docker Compose
- Poetry
- httpx
- Pytest
- Black, isort, and flake8

## API

Interactive API documentation is available after startup:

- Main service Swagger UI: `http://localhost:8000/docs`
- Main service ReDoc: `http://localhost:8000/redoc`
- External service Swagger UI: `http://localhost:8002/docs`

### Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/ping` | Application health check. |
| `GET` | `/ping/db` | PostgreSQL connection health check. |
| `POST` | `/auth/register` | Registers a user with email and password. |
| `POST` | `/auth/login` | Returns a JWT access token for valid credentials. |
| `GET` | `/auth/me` | Returns the current authenticated user. |
| `GET` | `/result` | Compatibility endpoint. Proxies a default request to external-service and returns `true` or `false`. |
| `POST` | `/result` | Compatibility endpoint. Proxies request data to external-service and returns `true` or `false`. |
| `POST` | `/query` | Checks cadastral data, stores request history for the current user, and returns the result. Requires Bearer auth. |
| `GET` | `/history` | Returns request history sorted by `created_at` descending. Regular users see only their own history. Requires Bearer auth. |
| `GET` | `/admin/users` | Returns users for administrators. Requires Bearer auth and `is_admin = true`. |
| `GET` | `/admin/history` | Returns all request history for administrators. Supports filters and pagination. Requires Bearer auth and `is_admin = true`. |
| `GET` | `/admin/history/{request_id}` | Returns one history record by id for administrators. Requires Bearer auth and `is_admin = true`. |

The external-service exposes:

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/result` | Accepts cadastral data, emulates processing delay, and returns `{"result": true}` or `{"result": false}`. |

### Validation

- `cadastral_number` must contain four numeric parts separated by colons,
  for example `77:01:0004012:2054`.
- `latitude` must be a finite number from `-90` to `90`.
- `longitude` must be a finite number from `-180` to `180`.
- `/history` supports `limit` from `1` to `500`; default is `100`.
- `/history` supports `offset` from `0`; default is `0`.
- `/admin/users` supports `limit` from `1` to `500` and `offset` from `0`;
  defaults are `100` and `0`.
- `/admin/history` supports `limit` from `1` to `500` and `offset` from `0`;
  defaults are `100` and `0`.
- `/admin/history` supports filters by `cadastral_number`, `user_id`, and
  `result`.
- Invalid input returns `422 Unprocessable Entity` with validation details.

### Authorization

- Passwords are stored as PBKDF2-HMAC-SHA256 hashes.
- `/auth/login` returns an HS256 JWT access token.
- Send protected requests with `Authorization: Bearer <access_token>`.
- Missing, invalid, expired, or inactive-user tokens return `401 Unauthorized`.
- `/query` and `/history` are protected. A regular user sees only records linked
  to their own `users.id`.
- `/admin/*` endpoints are protected by the same Bearer authentication and also
  require `users.is_admin = true`.
- A regular authenticated user receives `403 Forbidden` on `/admin/*`.
- An unauthenticated request receives `401 Unauthorized` on `/admin/*`.

## Environment

Create a `.env` file from `.env.example`:

```bash
cp .env.example .env
```

For Docker Compose, make sure `DATABASE_URL` uses the same database name,
user, and password as the PostgreSQL variables:

```env
DATABASE_URL=postgresql://postgres_user:postgres_password@db:5432/cadastral_check_service
APP_PORT=8000
EXTERNAL_SERVICE_URL=http://external-service:8001
EXTERNAL_SERVICE_TIMEOUT=2.0
EXTERNAL_SERVICE_PORT=8002
JWT_SECRET_KEY=change-this-secret
ACCESS_TOKEN_EXPIRE_MINUTES=30
POSTGRES_DB=cadastral_check_service
POSTGRES_USER=postgres_user
POSTGRES_PASSWORD=postgres_password
```

For a local app process outside Docker, set `DATABASE_URL` to a PostgreSQL
instance reachable from the host machine, for example:

```env
DATABASE_URL=postgresql://postgres_user:postgres_password@localhost:5432/cadastral_check_service
EXTERNAL_SERVICE_URL=http://localhost:8001
```

`EXTERNAL_SERVICE_TIMEOUT` is the main service timeout in seconds for calls to
external-service.

`JWT_SECRET_KEY` signs access tokens. Use a strong unique value in production.
`ACCESS_TOKEN_EXPIRE_MINUTES` controls access token lifetime.

## Run With Docker

Build and start the main application, external-service, and PostgreSQL:

```bash
docker compose up --build
```

The main app container runs database migrations automatically before starting
Uvicorn. The external-service container runs a separate FastAPI app from the
same image.

Check the service:

```bash
curl http://localhost:8000/ping
```

Expected response:

```json
{"status":"ok"}
```

Check external-service directly:

```bash
curl -X POST http://localhost:8002/result \
  -H "Content-Type: application/json" \
  -d '{
    "cadastral_number": "77:01:0004012:2054",
    "latitude": 55.7558,
    "longitude": 37.6173
  }'
```

Expected response:

```json
{"result":true}
```

Stop containers:

```bash
docker compose down
```

To remove the PostgreSQL volume as well:

```bash
docker compose down -v
```

## Run Locally

Install dependencies:

```bash
poetry install
```

Set `DATABASE_URL` in `.env` to a reachable PostgreSQL database.

Apply migrations:

```bash
poetry run python -m scripts.migrate
```

Start the app:

```bash
poetry run uvicorn app.main:app --reload
```

In a separate terminal, start the external-service:

```bash
poetry run uvicorn external_service.main:app --host 0.0.0.0 --port 8001 --reload
```

Check the service:

```bash
curl http://localhost:8000/ping
```

## Testing And Quality Checks

Run tests:

```bash
poetry run pytest
```

Run the full project checks:

```bash
poetry run black .
poetry run isort .
poetry run flake8
poetry run pytest
```

## Request Examples

### Health Check

```bash
curl http://localhost:8000/ping
```

Response:

```json
{"status":"ok"}
```

### Database Health Check

```bash
curl http://localhost:8000/ping/db
```

Response:

```json
{"status":"ok"}
```

### Main Service Compatibility Result Endpoint

```bash
curl http://localhost:8000/result
```

Response:

```json
true
```

POST is also supported:

```bash
curl -X POST http://localhost:8000/result \
  -H "Content-Type: application/json" \
  -d '{
    "cadastral_number": "77:01:0004012:2054",
    "latitude": 55.7558,
    "longitude": 37.6173
  }'
```

### External Result Emulator

```bash
curl -X POST http://localhost:8002/result \
  -H "Content-Type: application/json" \
  -d '{
    "cadastral_number": "77:01:0004012:2054",
    "latitude": 55.7558,
    "longitude": 37.6173
  }'
```

Response:

```json
{"result":true}
```

### Register

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "strong-password"
  }'
```

Response:

```json
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true,
  "is_admin": false,
  "created_at": "2026-01-01T12:00:00Z"
}
```

### Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "strong-password"
  }'
```

Response:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

Use the token in protected requests:

```bash
TOKEN="<jwt>"
```

### Current User

```bash
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

### Cadastral Query

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "cadastral_number": "77:01:0004012:2054",
    "latitude": 55.7558,
    "longitude": 37.6173
  }'
```

Response:

```json
{"result":true}
```

### Request History

```bash
curl http://localhost:8000/history \
  -H "Authorization: Bearer $TOKEN"
```

Response:

```json
[
  {
    "id": 1,
    "cadastral_number": "77:01:0004012:2054",
    "latitude": 55.7558,
    "longitude": 37.6173,
    "result": true,
    "created_at": "2026-01-01T12:00:00Z"
  }
]
```

Filter by cadastral number:

```bash
curl --get http://localhost:8000/history \
  -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "cadastral_number=77:01:0004012:2054"
```

Use pagination:

```bash
curl "http://localhost:8000/history?limit=25&offset=50" \
  -H "Authorization: Bearer $TOKEN"
```

### Admin API

Admin endpoints require a token for a user with `is_admin = true`:

```bash
ADMIN_TOKEN="<admin-jwt>"
```

List users:

```bash
curl "http://localhost:8000/admin/users?limit=100&offset=0" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Response:

```json
[
  {
    "id": 1,
    "email": "user@example.com",
    "is_active": true,
    "is_admin": false,
    "created_at": "2026-01-01T12:00:00Z"
  }
]
```

List all request history:

```bash
curl "http://localhost:8000/admin/history?limit=100&offset=0" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Filter admin history:

```bash
curl --get http://localhost:8000/admin/history \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  --data-urlencode "cadastral_number=77:01:0004012:2054" \
  --data-urlencode "user_id=1" \
  --data-urlencode "result=true" \
  --data-urlencode "limit=25" \
  --data-urlencode "offset=0"
```

Response:

```json
[
  {
    "id": 1,
    "user_id": 1,
    "cadastral_number": "77:01:0004012:2054",
    "latitude": 55.7558,
    "longitude": 37.6173,
    "result": true,
    "created_at": "2026-01-01T12:00:00Z"
  }
]
```

Open a single history record:

```bash
curl http://localhost:8000/admin/history/1 \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

## Project Structure

```text
app/
  api/admin.py           Admin API routes
  api/auth.py            Authentication routes
  api/dependencies.py    Shared FastAPI dependencies
  api/routes.py          API routes
  core/config.py         Environment-based settings
  core/database.py       asyncpg connection pool
  core/security.py       Password hashing and JWT helpers
  services/              External service clients
  main.py                FastAPI application
  schemas.py             Pydantic schemas and validators
external_service/        External FastAPI result emulator
migrations/              Raw SQL migrations
scripts/migrate.py       Migration runner
tests/                   Pytest test suite
Dockerfile               Application image
docker-compose.yml       Application and PostgreSQL services
```
