# Architecture Decision Records

## ADR-001: Use FastAPI For The HTTP API

Status: Accepted

### Problem

The service needs a clear HTTP API with request validation, generated OpenAPI
schema, asynchronous route support, and minimal framework overhead suitable for a
small backend test assignment.

### Decision

Use FastAPI for the main service and for the external-service emulator.

### Why This Option

FastAPI fits the project shape directly:

- Pydantic models are already the source of truth for request and response
  contracts.
- Swagger UI and ReDoc are generated automatically and available at `/docs` and
  `/redoc`.
- Async route handlers work naturally with `asyncpg` and `httpx.AsyncClient`.
- Dependency injection is simple enough for auth, admin checks, settings, and
  tests.
- The same framework can run the small external-service emulator without adding
  another stack.

### Alternatives Considered

- Flask: simpler, but async support, validation, and OpenAPI generation would
  require more manual wiring or extensions.
- Django/Django REST Framework: production-proven, but heavier than needed for a
  focused service with a small schema and direct SQL access.
- Starlette directly: lightweight and async-native, but would require more custom
  OpenAPI and validation code.

## ADR-002: Use `async/await`

Status: Accepted

### Problem

The main request path performs I/O-bound work: authenticating against PostgreSQL,
calling an external HTTP service, and writing request history. Blocking those
operations would reduce concurrency under parallel requests.

### Decision

Implement route handlers, database access, and external-service calls with
`async/await`.

### Why This Option

- FastAPI supports async route handlers natively.
- `asyncpg` and `httpx.AsyncClient` are async-native libraries.
- The service can wait on PostgreSQL and the external result provider without
  blocking the event loop thread.
- The design keeps the implementation simple while preserving production-style
  non-blocking I/O behavior.

### Alternatives Considered

- Synchronous route handlers with blocking database and HTTP clients: simpler for
  very small scripts but less suitable for concurrent web traffic.
- Background workers for external requests: useful for long-running jobs, but the
  current API contract returns the result synchronously.

## ADR-003: Use `asyncpg` For PostgreSQL Access

Status: Accepted

### Problem

The service needs efficient PostgreSQL access from async route handlers while
keeping the data layer explicit and easy to inspect.

### Decision

Use `asyncpg` directly with a shared connection pool stored in FastAPI
application state.

### Why This Option

- `asyncpg` is designed specifically for asynchronous PostgreSQL access.
- Parameterized SQL keeps queries safe from SQL injection while remaining easy to
  read in a small codebase.
- A shared pool avoids opening a new database connection for every request.
- Direct SQL makes the exact database behavior transparent for reviewers.

### Alternatives Considered

- SQLAlchemy ORM: useful for larger domain models, but would add abstraction not
  needed for two domain tables.
- SQLAlchemy Core async: a middle ground, but the current queries are small and
  clearer as raw SQL.
- psycopg synchronous access: mature, but would not match the async request path.

## ADR-004: Use Raw SQL Migrations Instead Of ORM Migrations

Status: Accepted

### Problem

The project needs repeatable schema setup without introducing an ORM or migration
framework that would be larger than the schema itself.

### Decision

Store migrations as ordered raw SQL files in `migrations/` and apply them through
`scripts/migrate.py`.

### Why This Option

- The schema is small and can be reviewed directly as SQL.
- Raw SQL exposes indexes, constraints, foreign keys, and PostgreSQL-specific
  behavior without hiding details behind a migration DSL.
- The migration runner records applied filenames in `schema_migrations`, making
  startup idempotent.
- Docker startup can run migrations before Uvicorn with a simple command.

### Alternatives Considered

- Alembic: powerful and standard with SQLAlchemy, but unnecessary without an ORM
  and for a compact schema.
- Manual database setup instructions only: fragile and easy to forget in Docker
  or CI-like environments.
- Recreating the schema on every startup: unsafe because it could destroy data.

## ADR-005: Use PostgreSQL

Status: Accepted

### Problem

The service persists users and request history and needs reliable constraints,
indexes, timestamps, and relational integrity.

### Decision

Use PostgreSQL as the primary database.

### Why This Option

- PostgreSQL supports the required relational model and foreign key behavior.
- `TIMESTAMPTZ`, `BIGSERIAL`, boolean fields, expression indexes, and robust
  constraints match the schema needs.
- The case-insensitive unique email index can be implemented directly with
  `UNIQUE INDEX ON users (LOWER(email))`.
- PostgreSQL is a common production backend choice and is easy to run locally via
  Docker Compose.

### Alternatives Considered

- SQLite: convenient for local development, but weaker for concurrent production
  writes and not equivalent to PostgreSQL behavior.
- MySQL/MariaDB: viable relational databases, but PostgreSQL expression indexes
  and `asyncpg` integration make PostgreSQL a cleaner fit here.
- In-memory storage: useful for prototypes but would not preserve history or
  support realistic authentication flows.

## ADR-006: Use Docker Compose For Local Runtime

Status: Accepted

### Problem

The project has multiple runtime processes: the main API, the external-service
emulator, and PostgreSQL. A reviewer should be able to start the full system with
minimal setup.

### Decision

Use Docker Compose with three services: `app`, `external-service`, and `db`.

### Why This Option

- Compose documents and starts the full local topology with one command.
- The main app can depend on the PostgreSQL health check and the external-service
  health check, so it starts after both dependencies are ready.
- Environment variables are centralized through `.env` and `docker-compose.yml`.
- The external emulator runs as a real network service, so integration behavior
  is close to a real provider call.

### Alternatives Considered

- Running every process manually: works, but creates more setup steps and more
  room for port or environment mistakes.
- A single container with all processes: simpler at first, but hides service
  boundaries and does not reflect how separate services communicate.
- Only local host dependencies: harder to reproduce consistently across machines.

## ADR-007: Use JWT Authentication

Status: Accepted

### Problem

Protected endpoints need stateless authentication for API clients and a way to
identify the current user on each request.

### Decision

Issue signed HS256 JWT access tokens from `/auth/login` and require bearer tokens
on protected API endpoints.

### Why This Option

- JWT access tokens allow stateless request authentication without server-side
  session storage.
- The token subject stores the user id; the service still loads the user from the
  database to enforce `is_active` and `is_admin` flags on every request.
- Expiration is configurable through `ACCESS_TOKEN_EXPIRE_MINUTES`.
- The same token format can be used by JSON API clients and the admin panel
  cookie.

### Alternatives Considered

- Server-side sessions: appropriate for browser-only applications, but less
  convenient for API clients and would require session storage.
- Basic authentication: simple, but sends credentials on every request and does
  not provide token expiration semantics.
- API keys: useful for service-to-service access, but not ideal for per-user
  login with active/admin checks.

## ADR-008: Emulate The External Service As A Separate Endpoint

Status: Accepted

### Problem

The main business flow depends on an external cadastral result provider, but a
test assignment must be runnable without access to a real third-party system.

### Decision

Implement `external_service/main.py` as a separate FastAPI app with `POST /result`
and call it from the main service through `EXTERNAL_SERVICE_URL`.

### Why This Option

- The main application exercises a real HTTP integration path through `httpx`,
  timeout handling, status handling, and response validation.
- Docker Compose makes the emulator a separate network service, preserving the
  boundary between internal application logic and external dependency.
- The emulator uses the same `QueryRequest` and `QueryResponse` contracts, so the
  integration contract stays explicit.
- Tests can still mock the service client where deterministic behavior is needed.

### Alternatives Considered

- Inline random result generation inside `/query`: simpler, but it would hide the
  external integration boundary and make timeout/unavailability handling less
  meaningful.
- A hardcoded mock object instead of an HTTP service: useful in tests, but less
  realistic for local end-to-end runs.
- Calling a real provider: not appropriate for a self-contained assignment and
  would make local development depend on third-party availability.
