# Cadastral Check Service

Backend service for cadastral checks. The service accepts a cadastral number,
latitude, and longitude, emulates an external cadastral check, stores the request
and boolean result in PostgreSQL, and exposes request history through an API.

## Stack

- Python 3.12+
- FastAPI with async routes
- PostgreSQL
- asyncpg
- Pydantic and pydantic-settings
- Raw SQL migrations
- Docker and Docker Compose
- Poetry
- Pytest
- Black, isort, and flake8

## API

Interactive API documentation is available after startup:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/ping` | Application health check. |
| `GET` | `/ping/db` | PostgreSQL connection health check. |
| `GET` | `/result` | External service emulator. Returns `true` or `false`. |
| `POST` | `/result` | External service emulator. Returns `true` or `false`. |
| `POST` | `/query` | Checks cadastral data, stores request history, and returns the result. |
| `GET` | `/history` | Returns stored request history sorted by `created_at` descending. |

### Validation

- `cadastral_number` must contain four numeric parts separated by colons,
  for example `77:01:0004012:2054`.
- `latitude` must be a finite number from `-90` to `90`.
- `longitude` must be a finite number from `-180` to `180`.
- `/history` supports `limit` from `1` to `500`; default is `100`.
- `/history` supports `offset` from `0`; default is `0`.
- Invalid input returns `422 Unprocessable Entity` with validation details.

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
POSTGRES_DB=cadastral_check_service
POSTGRES_USER=postgres_user
POSTGRES_PASSWORD=postgres_password
```

For a local app process outside Docker, set `DATABASE_URL` to a PostgreSQL
instance reachable from the host machine, for example:

```env
DATABASE_URL=postgresql://postgres_user:postgres_password@localhost:5432/cadastral_check_service
```

## Run With Docker

Build and start the application and PostgreSQL:

```bash
docker compose up --build
```

The Docker image runs database migrations automatically before starting Uvicorn.

Check the service:

```bash
curl http://localhost:8000/ping
```

Expected response:

```json
{"status":"ok"}
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

### External Result Emulator

```bash
curl http://localhost:8000/result
```

Response:

```json
true
```

POST is also supported:

```bash
curl -X POST http://localhost:8000/result
```

### Cadastral Query

```bash
curl -X POST http://localhost:8000/query \
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

### Request History

```bash
curl http://localhost:8000/history
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
  --data-urlencode "cadastral_number=77:01:0004012:2054"
```

Use pagination:

```bash
curl "http://localhost:8000/history?limit=25&offset=50"
```

## Project Structure

```text
app/
  api/routes.py          API routes
  core/config.py         Environment-based settings
  core/database.py       asyncpg connection pool
  main.py                FastAPI application
  schemas.py             Pydantic schemas and validators
migrations/              Raw SQL migrations
scripts/migrate.py       Migration runner
tests/                   Pytest test suite
Dockerfile               Application image
docker-compose.yml       Application and PostgreSQL services
```
