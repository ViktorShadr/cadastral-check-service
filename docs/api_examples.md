# API Examples

## Overview

The main service runs on `http://localhost:8000` by default when Docker Compose is
started with `.env.example` values. If `APP_PORT` is changed, use that host port
instead.

Interactive documentation is available from the running main service:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

The external-service emulator is exposed on `http://localhost:8002` by default
and has its own Swagger UI at `http://localhost:8002/docs`.

## Shared Schemas

### `QueryRequest`

```json
{
  "cadastral_number": "77:01:0004012:2054",
  "latitude": 55.7558,
  "longitude": 37.6173
}
```

Validation rules:

- `cadastral_number`: string with four numeric parts separated by colons;
  maximum length is 255 characters.
- `latitude`: JSON number from `-90` to `90`; strings and booleans are rejected.
- `longitude`: JSON number from `-180` to `180`; strings and booleans are
  rejected.

### `QueryResponse`

```json
{
  "result": true
}
```

### `UserPublic`

```json
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true,
  "is_admin": false,
  "created_at": "2026-01-01T12:00:00Z"
}
```

### `HistoryItem`

```json
{
  "id": 1,
  "cadastral_number": "77:01:0004012:2054",
  "latitude": 55.7558,
  "longitude": 37.6173,
  "result": true,
  "created_at": "2026-01-01T12:00:00Z"
}
```

### `AdminHistoryItem`

```json
{
  "id": 1,
  "user_id": 1,
  "cadastral_number": "77:01:0004012:2054",
  "latitude": 55.7558,
  "longitude": 37.6173,
  "result": true,
  "created_at": "2026-01-01T12:00:00Z"
}
```

## Authentication

Protected endpoints require a bearer token:

```http
Authorization: Bearer <access_token>
```

Common authentication and authorization errors:

```json
{"detail":"Not authenticated."}
```

```json
{"detail":"Invalid or expired token."}
```

```json
{"detail":"Inactive user."}
```

```json
{"detail":"Admin access required."}
```

## Health Endpoints

## `GET /ping`

Checks that the main HTTP process is alive.

### Request

```bash
curl http://localhost:8000/ping
```

### Successful Response

Status: `200 OK`

```json
{"status":"ok"}
```

### Possible Errors

This endpoint has no explicit application-level errors. Infrastructure failures
can still produce standard `5xx` responses.

## `GET /ping/db`

Checks that the main service can acquire a PostgreSQL connection and execute
`SELECT 1`.

### Request

```bash
curl http://localhost:8000/ping/db
```

### Successful Response

Status: `200 OK`

```json
{"status":"ok"}
```

### Possible Errors

- `500 Internal Server Error` if the database pool is unavailable or PostgreSQL
  rejects the health query.

## Auth Endpoints

## `POST /auth/register`

Creates a new user account. New users are active by default and are not admins by
default.

### Parameters

JSON body:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `email` | string | Yes | Valid email address, normalized to lowercase. |
| `password` | string | Yes | Password from 8 to 128 characters. |

### Request

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "User@Example.com",
    "password": "strong-password"
  }'
```

### Successful Response

Status: `201 Created`

```json
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true,
  "is_admin": false,
  "created_at": "2026-01-01T12:00:00Z"
}
```

### Possible Errors

- `409 Conflict` when the email is already registered.
- `422 Unprocessable Entity` when email or password validation fails.

```json
{"detail":"Email is already registered."}
```

## `POST /auth/login`

Authenticates an active user and returns a JWT access token.

### Parameters

JSON body:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `email` | string | Yes | Valid email address. |
| `password` | string | Yes | User password. |

### Request

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "strong-password"
  }'
```

### Successful Response

Status: `200 OK`

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

### Possible Errors

- `401 Unauthorized` for missing user, invalid password, or inactive user.
- `422 Unprocessable Entity` when request validation fails.

```json
{"detail":"Invalid email or password."}
```

## `GET /auth/me`

Returns the current authenticated user.

### Request

```bash
TOKEN="<jwt>"

curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

### Successful Response

Status: `200 OK`

```json
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true,
  "is_admin": false,
  "created_at": "2026-01-01T12:00:00Z"
}
```

### Possible Errors

- `401 Unauthorized` for missing, invalid, expired, or inactive-user token.

## Cadastral Result Endpoints

## `POST /query`

Runs an authenticated cadastral check, calls the external-service emulator, saves
the request history, and returns the boolean result.

### Parameters

Headers:

| Header | Required | Description |
| --- | --- | --- |
| `Authorization: Bearer <access_token>` | Yes | JWT returned by `/auth/login`. |

JSON body uses `QueryRequest`.

### Request

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

### Successful Response

Status: `200 OK`

```json
{"result":true}
```

### Possible Errors

- `401 Unauthorized` for missing, invalid, expired, or inactive-user token.
- `422 Unprocessable Entity` for invalid cadastral number or coordinates.
- `502 Bad Gateway` when the external service is unavailable or returns an
  invalid response.
- `504 Gateway Timeout` when the external service request exceeds the configured
  timeout.

```json
{"detail":"External service is unavailable."}
```

```json
{"detail":"External service returned an invalid response."}
```

```json
{"detail":"External service request timed out."}
```

## `POST /result`

Compatibility endpoint. Proxies the supplied cadastral request to the external
result service and returns a raw JSON boolean. It does not require authentication
and does not persist history.

### Parameters

Required JSON body uses `QueryRequest`.

### Request

```bash
curl -X POST http://localhost:8000/result \
  -H "Content-Type: application/json" \
  -d '{
    "cadastral_number": "77:01:0004012:2055",
    "latitude": 55.7559,
    "longitude": 37.6174
  }'
```

### Successful Response

Status: `200 OK`

```json
false
```

### Possible Errors

- `422 Unprocessable Entity` for invalid request body.
- `502 Bad Gateway` when the external service is unavailable or returns an
  invalid response.
- `504 Gateway Timeout` when the external service request exceeds the configured
  timeout.

## History Endpoints

## `GET /history`

Returns cadastral request history visible to the current authenticated user.
Regular users see only their own records. Admin users can see all records through
this endpoint, but the response schema still omits `user_id`.

### Parameters

Headers:

| Header | Required | Description |
| --- | --- | --- |
| `Authorization: Bearer <access_token>` | Yes | JWT returned by `/auth/login`. |

Query parameters:

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `cadastral_number` | string | No | none | Optional cadastral number filter. |
| `limit` | integer | No | `100` | Number of rows to return, from `1` to `500`. |
| `offset` | integer | No | `0` | Number of matching rows to skip, from `0`. |

### Request

```bash
curl http://localhost:8000/history \
  -H "Authorization: Bearer $TOKEN"
```

### Filtered Request

```bash
curl --get http://localhost:8000/history \
  -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "cadastral_number=77:01:0004012:2054" \
  --data-urlencode "limit=25" \
  --data-urlencode "offset=0"
```

### Successful Response

Status: `200 OK`

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

### Possible Errors

- `401 Unauthorized` for missing, invalid, expired, or inactive-user token.
- `422 Unprocessable Entity` for invalid filter, limit, or offset.

## `GET /history/{cadastral_number}`

A separate path endpoint with this shape is not implemented in the current
project. The implemented API exposes the same user-facing lookup as a query
parameter on `GET /history`:

```bash
curl --get http://localhost:8000/history \
  -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "cadastral_number=77:01:0004012:2054"
```

This note is intentional: documenting `GET /history/{cadastral_number}` as an
active route would not match the actual FastAPI router in `app/api/routes.py`.

## Admin JSON API

Admin API endpoints require an active user with `is_admin = true`.

There is no public admin-registration endpoint. The current workflow is to create
a regular user through `/auth/register` and promote it in PostgreSQL:

```sql
UPDATE users SET is_admin = true WHERE email = 'admin@example.com';
```

## `GET /admin/users`

Returns users sorted by `created_at DESC, id DESC`.

### Parameters

Headers:

| Header | Required | Description |
| --- | --- | --- |
| `Authorization: Bearer <admin_access_token>` | Yes | JWT for a user with `is_admin = true`. |

Query parameters:

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `limit` | integer | No | `100` | Number of users to return, from `1` to `500`. |
| `offset` | integer | No | `0` | Number of users to skip, from `0`. |

### Request

```bash
ADMIN_TOKEN="<admin-jwt>"

curl "http://localhost:8000/admin/users?limit=100&offset=0" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Successful Response

Status: `200 OK`

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

### Possible Errors

- `401 Unauthorized` for missing, invalid, expired, or inactive-user token.
- `403 Forbidden` when the authenticated user is not an admin.
- `422 Unprocessable Entity` for invalid `limit` or `offset`.

## `GET /admin/history`

Returns all request history for administrators, with optional filters.

### Parameters

Headers:

| Header | Required | Description |
| --- | --- | --- |
| `Authorization: Bearer <admin_access_token>` | Yes | JWT for a user with `is_admin = true`. |

Query parameters:

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `cadastral_number` | string | No | none | Optional cadastral number filter. |
| `user_id` | integer | No | none | Optional owner user id filter, from `1`. |
| `result` | boolean | No | none | Optional result filter. |
| `limit` | integer | No | `100` | Number of rows to return, from `1` to `500`. |
| `offset` | integer | No | `0` | Number of rows to skip, from `0`. |

### Request

```bash
curl "http://localhost:8000/admin/history?limit=100&offset=0" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Filtered Request

```bash
curl --get http://localhost:8000/admin/history \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  --data-urlencode "cadastral_number=77:01:0004012:2054" \
  --data-urlencode "user_id=1" \
  --data-urlencode "result=true" \
  --data-urlencode "limit=25" \
  --data-urlencode "offset=0"
```

### Successful Response

Status: `200 OK`

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

### Possible Errors

- `401 Unauthorized` for missing, invalid, expired, or inactive-user token.
- `403 Forbidden` when the authenticated user is not an admin.
- `422 Unprocessable Entity` for invalid filters, limit, or offset.

## `GET /admin/history/{request_id}`

Returns one history record by database id.

### Parameters

Path parameters:

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `request_id` | integer | Yes | History record id, from `1`. |

Headers:

| Header | Required | Description |
| --- | --- | --- |
| `Authorization: Bearer <admin_access_token>` | Yes | JWT for a user with `is_admin = true`. |

### Request

```bash
curl http://localhost:8000/admin/history/1 \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Successful Response

Status: `200 OK`

```json
{
  "id": 1,
  "user_id": 1,
  "cadastral_number": "77:01:0004012:2054",
  "latitude": 55.7558,
  "longitude": 37.6173,
  "result": true,
  "created_at": "2026-01-01T12:00:00Z"
}
```

### Possible Errors

- `401 Unauthorized` for missing, invalid, expired, or inactive-user token.
- `403 Forbidden` when the authenticated user is not an admin.
- `404 Not Found` when the history record does not exist.
- `422 Unprocessable Entity` when `request_id` is less than `1`.

```json
{"detail":"History request not found."}
```

## Admin Panel Endpoints

The admin panel returns HTML pages rendered with Jinja2 templates. Panel pages can
authenticate through either a bearer token or an HttpOnly cookie named
`admin_panel_token`. Browser login creates the cookie with path `/admin/panel`.

## `GET /admin/panel/login`

Renders the admin login form.

### Request

```bash
curl http://localhost:8000/admin/panel/login
```

### Successful Response

Status: `200 OK`

Content type: `text/html`

### Possible Errors

This endpoint has no explicit application-level errors.

## `POST /admin/panel/login`

Authenticates an active admin user from form-encoded credentials and redirects to
`/admin/panel` with an HttpOnly cookie.

### Parameters

Form fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `email` | string | Yes | Admin email. |
| `password` | string | Yes | Admin password. |

### Request

```bash
curl -i -X POST http://localhost:8000/admin/panel/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "email=admin@example.com" \
  --data-urlencode "password=admin-password"
```

### Successful Response

Status: `303 See Other`

Headers include:

```http
Location: /admin/panel
Set-Cookie: admin_panel_token=<jwt>; HttpOnly; Path=/admin/panel; SameSite=lax
```

### Possible Errors

- `400 Bad Request` rendered HTML when email or password is missing.
- `401 Unauthorized` rendered HTML for invalid credentials.
- `403 Forbidden` rendered HTML when the user is not an admin.

## `POST /admin/panel/logout`

Clears the admin panel cookie and redirects to the login form.

### Request

```bash
curl -i -X POST http://localhost:8000/admin/panel/logout
```

### Successful Response

Status: `303 See Other`

```http
Location: /admin/panel/login
```

## `GET /admin/panel`

Renders the admin dashboard.

### Request With Bearer Token

```bash
curl http://localhost:8000/admin/panel \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Successful Response

Status: `200 OK`

Content type: `text/html`

### Possible Errors

- `401 Unauthorized` for missing or invalid auth.
- `403 Forbidden` when the authenticated user is not an admin.

## `GET /admin/panel/users`

Renders an HTML table with users.

### Query Parameters

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `limit` | integer | No | `100` | Number of users to render, from `1` to `500`. |
| `offset` | integer | No | `0` | Number of users to skip, from `0`. |

### Request

```bash
curl "http://localhost:8000/admin/panel/users?limit=100&offset=0" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Successful Response

Status: `200 OK`

Content type: `text/html`

### Possible Errors

- `401 Unauthorized` for missing or invalid auth.
- `403 Forbidden` when the authenticated user is not an admin.
- `422 Unprocessable Entity` for invalid pagination.

## `GET /admin/panel/history`

Renders an HTML table with request history and optional user email loaded through
a left join with `users`.

### Query Parameters

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `limit` | integer | No | `100` | Number of history rows to render, from `1` to `500`. |
| `offset` | integer | No | `0` | Number of history rows to skip, from `0`. |

### Request

```bash
curl "http://localhost:8000/admin/panel/history?limit=100&offset=0" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Successful Response

Status: `200 OK`

Content type: `text/html`

### Possible Errors

- `401 Unauthorized` for missing or invalid auth.
- `403 Forbidden` when the authenticated user is not an admin.
- `422 Unprocessable Entity` for invalid pagination.

## `GET /admin/panel/history/{request_id}`

Renders an HTML detail page for one request history row.

### Parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `request_id` | integer | Yes | History record id, from `1`. |

### Request

```bash
curl http://localhost:8000/admin/panel/history/1 \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Successful Response

Status: `200 OK`

Content type: `text/html`

### Possible Errors

- `401 Unauthorized` for missing or invalid auth.
- `403 Forbidden` when the authenticated user is not an admin.
- `404 Not Found` when the history record does not exist.
- `422 Unprocessable Entity` when `request_id` is less than `1`.

## External-Service Emulator

## `POST /result` on `external_service.main`

This endpoint belongs to the external-service emulator, not to the main app. It
accepts `QueryRequest`, waits briefly, and returns `QueryResponse`.

### Request

```bash
curl -X POST http://localhost:8002/result \
  -H "Content-Type: application/json" \
  -d '{
    "cadastral_number": "77:01:0004012:2054",
    "latitude": 55.7558,
    "longitude": 37.6173
  }'
```

### Successful Response

Status: `200 OK`

```json
{"result":true}
```

### Possible Errors

- `422 Unprocessable Entity` for invalid cadastral number or coordinates.
