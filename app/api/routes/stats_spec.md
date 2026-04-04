# Specification: app/api/routes/stats.py

## Purpose

Router for the "Dashboard" module — provides aggregated statistics and chart data based on the `logs` table. Implements the file `app/api/routes/stats.py`.

---

## §1. General Information

- **Prefix**: `/api/stats`
- **OpenAPI Tags**: `["Stats"]`
- **Authentication**: all endpoints are protected by the `get_current_user` dependency (HTTP Basic Auth).
- **Dependencies**: `LogService` (via DI factory `get_log_service`).

---

## §2. Endpoint: GET /api/stats/summary

### §2.1 Purpose

Returns summary statistics for the main dashboard: total event count, chat request count, guardrail incident count, system error count, total token count, and average latency.

### §2.2 Request Parameters

No parameters (besides authentication).

### §2.3 Result Caching (Performance)

The endpoint calls a heavy aggregation (`aggregate_token_stats()`), which loads records from the `logs` table for JSON parsing. To prevent DoS and OOM as the table grows:
- The `get_stats_summary()` result MUST be cached in an in-memory cache with TTL = 60 seconds.
- The cache is stored as a module variable (dict with `result` and `timestamp` keys).
- Repeated calls within the TTL return the cached result without DB access.
- The cache is automatically invalidated upon TTL expiration.

### §2.4 Parallel Request Protection (Availability)

The heavy aggregation query MUST NOT be executed in parallel by multiple simultaneous requests. To prevent DB connection pool exhaustion:
- Use an async lock at the endpoint or service level.
- If the lock is already held by another request — wait for its release (do not reject the request).
- This guarantees that at most one aggregation query is executing against the DB at any given time.

### §2.5 Processing Algorithm

1. Check the in-memory cache. If the cache is valid (age < 60 seconds) — return the cached result.
2. Acquire the async lock (see §2.4).
3. Re-check the cache (double-check after lock acquisition — another request may have updated the cache while we were waiting).
4. Call the `log_service.get_stats_summary()` method.
5. The service method returns a dict with keys:
   - `total` — integer, total record count in the logs table.
   - `chat_requests` — integer, record count with event_type equal to "chat_request".
   - `guardrail_incidents` — integer, record count with event_type equal to "guardrail_incident".
   - `system_errors` — integer, record count with event_type equal to "system_error".
   - `total_tokens` — integer, sum of all tokens extracted from the JSON payload field of each record (path: `response.usage.total_tokens`). If the field is absent or not a number — the record is skipped (contribution = 0).
   - `avg_latency_ms` — float (rounded to 2 decimal places), average latency in milliseconds. Computed from the JSON payload field of each record (path: `response.latency_ms`). If the field is absent — the record does not participate in the average calculation. If no records contain latency — return 0.0.
6. Save the result to cache with the current timestamp.
7. Release the lock.
8. Return the result as a JSON response with status 200.

### §2.6 Response Format (HTTP 200)

Dict with six keys: `total`, `chat_requests`, `guardrail_incidents`, `system_errors`, `total_tokens`, `avg_latency_ms`. All values are numbers.

### §2.7 Error Handling

- On any exception from the service layer — return HTTP 500 with body containing key `detail` and string value "Internal server error".
- trace_id in the error response is mandatory: generate UUID v4.

---

## §3. Endpoint: GET /api/stats/charts

### §3.1 Purpose

Returns data for building an activity chart — event counts grouped by hour for the last 24 hours.

### §3.2 Request Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `hours` | int | No | 24 | Number of hours back from the current moment. Allowed range: 1 to 168 (7 days). Validation: value MUST be >= 1 and <= 168. Validation is performed at the FastAPI Query level with parameters ge=1, le=168. |

### §3.3 Index Requirement

The SQL query filters by `created_at >= since` and groups by formatted date. To prevent full table scans, the `logs.created_at` column MUST have an index (see `repositories_upgrade_spec.md` §2.5).

### §3.4 Processing Algorithm

1. Call the `log_service.get_chart_data(hours=hours)` method.
2. The service method returns a list of dicts, each containing:
   - `hour` — string in "YYYY-MM-DD HH:00" format (start of the hourly interval).
   - `count` — integer, record count in that hourly interval.
3. The list is sorted by `hour` in ascending order (oldest to newest).
4. If a particular hourly interval has no records — that interval is NOT included in the result (sparse format). Filling gaps with zeros is the frontend's responsibility.
5. Return the result as a JSON array with status 200.

### §3.5 Response Format (HTTP 200)

JSON array of dicts with keys `hour` (string) and `count` (integer).

### §3.6 Error Handling

- On any exception from the service layer — return HTTP 500 with body containing key `detail` and string value "Internal server error".
- trace_id in the error response is mandatory: generate UUID v4.

---

## §4. Security

- All endpoints require HTTP Basic Auth via the `get_current_user` dependency.
- Timing-safe comparison is used (implemented in middleware).
- Rate limiting is applied at the middleware level (5 failed attempts in 60 seconds → HTTP 429).
- The `/api/stats/summary` endpoint is protected by caching (TTL=60s) and an async lock to prevent DoS via parallel heavy queries (see §2.3, §2.4).
- The `hours` parameter is validated at the FastAPI Query level (ge=1, le=168) to prevent excessively broad queries.
