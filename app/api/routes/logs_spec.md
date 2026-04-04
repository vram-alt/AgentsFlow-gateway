# Specification: Event Log Router (logs.py)

> **Implementation file:** `logs.py`  
> **Layer:** API / Delivery  
> **Responsibility:** HTTP handlers for viewing the event log, statistics, export, and replay

---

## 1. General Rules

- Routes are thin wrappers: accept an HTTP request, call the service, return an HTTP response.
- Business logic is **prohibited** in routes — only routing and transformation.
- All dependencies are obtained via FastAPI Depends.

---

## 2. Router

**Prefix:** `/api/logs`  
**Tags:** "Logs"  
**Protection:** HTTP Basic Auth.

**Important: endpoint registration order.** Endpoints with static paths (`/export`, `/stats`) MUST be registered BEFORE endpoints with path parameters (`/{trace_id}`, `/{id}/replay`), otherwise FastAPI interprets static segments as parameter values.

---

## 3. Endpoint: GET /api/logs/

### Purpose

Paginated list of log events with optional trace_id search.

### Query Parameters

| Parameter    | Type                  | Default      | Constraints              | Description                 |
|--------------|-----------------------|--------------|--------------------------|-----------------------------|
| `limit`      | integer               | 100          | min 1, max 1000          | Number of records           |
| `offset`     | integer               | 0            | min 0                    | Offset                      |
| `event_type` | string or None        | None         | —                        | Filter by event type        |
| `trace_id`   | string or None        | None         | UUID v4 format           | Search by trace_id          |

### DoS Protection

The limit parameter must have an upper bound (maximum 1000) to prevent full table scans and memory exhaustion. The offset parameter cannot be negative. Validation of both parameters is performed at the Pydantic request schema level. The maximum allowed limit value should be externalized to application configuration.

### trace_id Validation

If `trace_id` is provided and non-empty — validate it as UUID v4. Validation is performed by attempting to parse the string as a UUID with error handling. If the string is not a valid UUID — return HTTP 422 with error description "Invalid trace_id format, expected UUID v4". This prevents passing arbitrary strings to the data layer.

### Step-by-Step Logic

1. If `trace_id` is provided and non-empty:
   - Validate UUID format.
   - Call `log_service.get_logs_by_trace_id(trace_id)`.
   - Return the result (ignoring `limit`, `offset`, `event_type`).
2. If `trace_id` is not provided:
   - Execute existing logic (call `log_service.get_logs(limit, offset, event_type)`).

---

## 4. Endpoint: GET /api/logs/export

### Purpose

Export log records in CSV format. Returns a streaming response (StreamingResponse) for efficient transfer of large data volumes.

### Request Parameters

| Parameter    | Type           | Required | Default      | Description                                                              |
|--------------|----------------|----------|--------------|--------------------------------------------------------------------------|
| `event_type` | string or None | No       | None         | Filter by event type. If provided — export only this type.               |
| `limit`      | integer        | No       | 5000         | Maximum number of records. Range: 1–50000.                               |

### Processing Algorithm

1. Call `log_service.export_logs(event_type=event_type, limit=limit)`.
2. The service method returns an async generator of CSV strings. The generator uses streaming from the repository (server-side cursor), preventing loading all records into memory.
3. Return `StreamingResponse` with:
   - `media_type` = "text/csv"
   - Header `Content-Disposition` = "attachment; filename=logs_export.csv"

### CSV Format

First row — column headers: `id`, `trace_id`, `event_type`, `created_at`, `payload`.

Each subsequent row — one log record:
- `id` — integer.
- `trace_id` — string (UUID).
- `event_type` — string.
- `created_at` — string in ISO 8601 format.
- `payload` — JSON string (escaped for CSV). CSV Injection protection: if a string value starts with characters `=`, `+`, `-`, `@`, `\t`, `\r` — a single quote prefix is prepended. This prevents formula execution when the CSV is opened in Excel.

### Export Error Handling

- On service layer error — HTTP 500 with `detail` key.
- If the error occurs after streaming has started (HTTP headers already sent) — an error marker string `# ERROR: export interrupted` is appended to the end of the CSV stream.

---

## 5. Endpoint: GET /api/logs/stats

### Purpose

Event statistics for the dashboard.

### Step-by-Step Logic

1. Call log_service.get_log_stats().
2. Return HTTP 200 with the statistics dict.

---

## 6. Endpoint: GET /api/logs/{trace_id}

### Purpose

All events for a specific trace_id.

### Step-by-Step Logic

1. Call log_service.get_logs_by_trace_id(trace_id).
2. Return HTTP 200 with the list of related events.

---

## 7. Endpoint: POST /api/logs/{id}/replay

### Purpose

Replays a previously executed chat request. Extracts the original request parameters from the log record payload and resubmits them via ChatService.

### Path Parameters

| Parameter | Type | Description                                               |
|-----------|------|-----------------------------------------------------------|
| `id`      | int  | Numeric primary key of the log record (LogEntryModel.id)  |

### Dependencies

- `LogService` — via DI factory `get_log_service`.
- `ChatService` — via DI factory `get_chat_service`.

### Rate Limiting (Abuse Protection)

The replay endpoint allows resending a request to the LLM provider, which incurs API key costs. To prevent abuse:
- Maximum 10 replay requests per minute per user. On exceeding — return HTTP 429 with body containing `detail` = "Rate limit exceeded for replay requests".
- Rate limit is implemented via an in-memory dict with key = username and value = list of timestamps of recent requests. Entries older than 60 seconds are purged on each check.

### Processing Algorithm

1. Check rate limit. On exceeding — return HTTP 429.
2. Call `log_service.get_log_by_id(id)` to retrieve the log record.
3. If record not found — return HTTP 404 with body containing `detail` = "Log entry not found".
4. If the record's `event_type` is not "chat_request" — return HTTP 400 with body containing `detail` = "Only chat_request logs can be replayed".
5. Extract original request parameters from `payload` (JSON):
   - `payload.prompt.model` — string, model.
   - `payload.prompt.messages` — list of dicts with `role` and `content` keys.
   - `payload.prompt.temperature` — number or None.
   - `payload.prompt.max_tokens` — integer or None.
   - `payload.prompt.guardrail_ids` — list of strings or empty list.
6. **Extracted data validation**: data extracted from payload MUST be validated via the `ChatRequest` Pydantic schema before sending to `ChatService`. If the payload is corrupted or modified and fails validation — return HTTP 400 with body containing `detail` = "Original request data is incomplete for replay".
7. Log the replay event at INFO level with `is_replay=true` annotation, specifying the `log_id` of the original record and the username (for auditing).
8. Call `chat_service.send_chat_message()` with the validated parameters.
9. If result is GatewayError — return the corresponding HTTP status and error body.
10. If result is UnifiedResponse — return HTTP 200 with the serialized response.

### Response Format (HTTP 200)

Identical to the POST /api/chat/send response format:
- `trace_id` — string (new UUID, not the original).
- `content` — string, model response.
- `model` — string.
- `usage` — dict with tokens or null.
- `guardrail_blocked` — boolean.

---

## 8. Security

- All endpoints require HTTP Basic Auth via the `get_current_user` dependency.
- The `trace_id` parameter is validated as UUID v4.
- Replay creates a NEW trace_id (does not reuse the original).
- Replay is protected by rate limiting: maximum 10 requests per minute per user.
- Each replay is logged with `is_replay=true` annotation for auditing.
- Data from payload is validated via Pydantic schema before sending to ChatService.
- CSV export contains sensitive data from payload — access is restricted by authentication.
- CSV values are escaped for CSV Injection protection.
- Default `limit` value for export is reduced to 5000 to limit memory consumption.

---

## 9. Error Handling

| HTTP Status | When                                                         |
|-------------|--------------------------------------------------------------|
| 200         | Successful operation                                         |
| 400         | Event type is not chat_request / data incomplete for replay  |
| 401         | Invalid token / unauthorized                                 |
| 404         | Log record not found (replay)                                |
| 422         | Invalid query parameters / invalid trace_id                  |
| 429         | Rate limit exceeded for replay requests                      |
| 500         | Internal server error                                        |
