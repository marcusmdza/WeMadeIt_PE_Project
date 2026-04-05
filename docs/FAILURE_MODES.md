# Failure Modes

Documents how the app behaves under error conditions and how each failure is recovered from.

---

## 1. Database Unavailable

| Field | Detail |
|---|---|
| **Trigger** | PostgreSQL is down, unreachable, or the connection pool is exhausted |
| **Expected Behavior** | Any route that touches the DB catches `peewee.DatabaseError` and returns a JSON error body. The exception and full traceback are logged via `logger.exception()`. The redirect route (`GET /<short_code>`) catches the lookup failure but also tries to isolate the `click_count` increment — if only the increment fails the redirect still fires. |
| **Status Code** | `503 Service Unavailable` |
| **Response Body** | `{"error": "Service temporarily unavailable"}` |
| **Recovery Method** | The DB connection is managed per-request via `before_request` / `teardown_appcontext` hooks, so each new request gets a fresh connection attempt. No app restart is needed — the app recovers automatically once the database becomes reachable again. The `/metrics` endpoint reports `"database_status": "disconnected"` while the DB is down, making it easy to detect via health monitoring. |

---

## 2. Invalid Input — Missing or Malformed URL

| Field | Detail |
|---|---|
| **Trigger** | `POST /shorten` is called with no `"url"` field, an empty string, or a URL that does not start with `http://` or `https://` |
| **Expected Behavior** | The route validates input before touching the database and returns immediately with a descriptive error message. |
| **Status Code** | `400 Bad Request` |
| **Response Body** | `{"error": "URL is required"}` — when the field is absent or empty |
| | `{"error": "URL must start with http:// or https://"}` — when the scheme is invalid |
| **Recovery Method** | Client-side fix required. The app is stateless with respect to this error — no partial writes occur. |

---

## 3. Duplicate Short Code Collision

| Field | Detail |
|---|---|
| **Trigger** | The randomly generated 6-character `short_code` already exists in the database (probability is low but non-zero at scale) |
| **Expected Behavior** | The `POST /shorten` route catches `peewee.IntegrityError` on the `INSERT` and retries with a newly generated code. This happens up to 3 times transparently. If all 3 attempts collide (extremely unlikely), a 500 is returned. |
| **Status Code** | `201 Created` on success (client never sees the retry); `500 Internal Server Error` after 3 failed attempts |
| **Response Body** | Normal URL object on success; `{"error": "Failed to generate a unique short code, please retry"}` after exhausted retries |
| **Recovery Method** | Automatic — retries are handled inside the request with no client involvement. The uniqueness constraint is enforced at the database level (`UNIQUE` on `short_code`), so no duplicate can slip through even under concurrent load. |

---

## 4. Inactive URL Accessed

| Field | Detail |
|---|---|
| **Trigger** | `GET /<short_code>` is called for a URL where `is_active = False` (soft-deleted via `DELETE /urls/<id>`) |
| **Expected Behavior** | The record is found in the database but the `is_active` flag is checked before redirecting. The click counter is not incremented. |
| **Status Code** | `410 Gone` |
| **Response Body** | `{"error": "This URL is no longer active"}` |
| **Recovery Method** | No automatic recovery — `410` signals permanent removal. A `PUT /urls/<id>` with `{"is_active": true}` can reactivate the URL if needed. |

---

## 5. App Process Killed

| Field | Detail |
|---|---|
| **Trigger** | The gunicorn process crashes (OOM, unhandled signal, fatal exception) or the container exits unexpectedly |
| **Expected Behavior** | In-flight requests are dropped. The Docker `restart: always` policy on the `app` service detects the exit and relaunches the container automatically. |
| **Status Code** | TCP connection refused or reset while the container is restarting |
| **Recovery Method** | Docker restarts the container with exponential backoff (1s, 2s, 4s, …). The app is stateless — no in-memory state needs to be rebuilt. The database connection is re-established on the first incoming request via the `before_request` hook. Typical recovery time is a few seconds. |

---

## 6. Nonexistent Short Code

| Field | Detail |
|---|---|
| **Trigger** | `GET /<short_code>` is called with a code that has no matching row in the database |
| **Expected Behavior** | `peewee.DoesNotExist` is caught and a JSON 404 is returned immediately. No redirect is attempted. |
| **Status Code** | `404 Not Found` |
| **Response Body** | `{"error": "URL not found"}` |
| **Recovery Method** | No recovery needed — this is expected behaviour for stale links or manual URL entry. |

---

## 7. Malformed JSON Body

| Field | Detail |
|---|---|
| **Trigger** | `POST /shorten` receives a request with a non-JSON `Content-Type` (e.g. `text/plain`) or a body that is not valid JSON |
| **Expected Behavior** | `request.get_json(silent=True)` returns `None` instead of raising. The route falls back to an empty dict (`{}`), finds no `"url"` key, and returns the missing-URL error. No exception is raised and no stack trace is logged. |
| **Status Code** | `400 Bad Request` |
| **Response Body** | `{"error": "URL is required"}` |
| **Recovery Method** | Client-side fix required — send `Content-Type: application/json` with a valid JSON body. |
