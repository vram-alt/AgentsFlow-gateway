# Specification: Logging Service (LogService)

> **Implementation file:** `log_service.py`  
> **Layer:** Services / Use Cases  
> **Responsibility:** Unified logging of all system events (chat, incidents, errors), export, and analytics

---

## 1. General Rules

- The service is the **single entry point** for writing any events to the audit log.
- All write methods are asynchronous, intended to be called from `BackgroundTasks`.
- Logging errors are **never propagated** to the caller — they are suppressed and written to stderr.
- Serialization of `payload` (dict → JSON string) is delegated to `LogRepository`.

---

## 2. Class: LogService

### Dependencies (via constructor)

| Parameter   | Type             | Description                                 |
|-------------|------------------|---------------------------------------------|
| `log_repo`  | `LogRepository`  | Repository for writing to the `logs` table  |

---

## 3. Method: log_chat_request

### Purpose

Record a prompt submission and LLM response event.

### Interface Description

- **Async method** accepting the following parameters:
  - `trace_id` (string) — request correlation identifier.
  - `prompt_data` (dict) — submitted prompt data.
  - `response_data` (dict) — received response data.
  - `is_error` (boolean, default False) — error response flag.
- **Returns:** nothing.

### Step-by-Step Logic

1. **Build payload** — a dict with the following keys:
   - `prompt` — submitted prompt data (from `prompt_data` parameter)
   - `response` — received response data (from `response_data` parameter)
   - `is_error` — flag indicating whether the response was an error (from `is_error` parameter)
   - `logged_at` — current datetime in ISO 8601 format (UTC)

2. **Write to DB:**
   - `event_type = EventType.CHAT_REQUEST`
   - Call `log_repo.create(trace_id, event_type, payload)`.

3. **On write error:** suppress the exception, output to stderr via `logging.error(...)`.

---

## 4. Method: log_guardrail_incident

### Purpose

Record a Guardrail trigger event (from webhook).

### Interface Description

- **Async method** accepting two parameters: `trace_id` (string — correlation identifier) and `incident_data` (dict — incident data).
- **Returns:** nothing.

### Step-by-Step Logic

1. **Build payload** — a dict with the following keys:
   - `incident` — incident data (from `incident_data` parameter)
   - `logged_at` — current datetime in ISO 8601 format (UTC)

2. **Write to DB:**
   - `event_type = EventType.GUARDRAIL_INCIDENT`
   - Call `log_repo.create(trace_id, event_type, payload)`.

3. **On write error:** suppress, log to stderr.

---

## 5. Method: log_system_error

### Purpose

Record a system error (adapter failure, DB error, etc.).

### Interface Description

- **Async method** accepting two parameters: `trace_id` (string — correlation identifier) and `error_data` (dict — error data).
- **Returns:** nothing.

### Step-by-Step Logic

1. **Build payload** — a dict with the following keys:
   - `error` — error data (from `error_data` parameter)
   - `logged_at` — current datetime in ISO 8601 format (UTC)

2. **Write to DB:**
   - `event_type = EventType.SYSTEM_ERROR`
   - Call `log_repo.create(trace_id, event_type, payload)`.

3. **On write error:** suppress, log to stderr.

---

## 6. Method: get_logs

### Purpose

Retrieve a list of events for display in the UI log viewer.

### Interface Description

- **Async method** accepting the following parameters:
  - `limit` (integer, default 100) — number of records.
  - `offset` (integer, default 0) — offset.
  - `event_type` (string or absent) — filter by event type.
- **Returns:** list of LogEntry domain entities.

### Step-by-Step Logic

1. If `event_type` is provided → call `log_repo.list_by_type(event_type, limit, offset)`.
2. Otherwise → call `log_repo.list_all(limit, offset)`.
3. Convert ORM models to `LogEntry` domain entities.
4. Return the list.

---

## 7. Method: get_logs_by_trace_id

### Purpose

Retrieve all events by correlation `trace_id` (for linking prompts with incidents).

### Interface Description

- **Async method** accepting one parameter: `trace_id` (string — correlation identifier).
- **Returns:** list of LogEntry domain entities.

### Step-by-Step Logic

1. Call `log_repo.get_by_trace_id(trace_id)`.
2. Convert to domain entities.
3. Return the list (may contain `chat_request` + `guardrail_incident`).

---

## 8. Method: get_log_stats

### Purpose

Retrieve statistics for the dashboard (event counts by type).

### Interface Description

- **Async method** with no parameters.
- **Returns:** dict with event type statistics.

### Returns

A dict with the following keys:

| Key                     | Type    | Description                               |
|-------------------------|---------|-------------------------------------------|
| `total`                 | integer | Total number of records in the log        |
| `chat_requests`         | integer | Number of CHAT_REQUEST events             |
| `guardrail_incidents`   | integer | Number of GUARDRAIL_INCIDENT events       |
| `system_errors`         | integer | Number of SYSTEM_ERROR events             |

---

## 9. Method: get_stats_summary

### Purpose

Extended dashboard statistics. Includes all data from the existing `get_log_stats()` plus aggregated token and latency data.

### Interface Description

- **Async method** with no parameters.
- **Returns:** dict with six keys.

### Algorithm

1. Call the existing method `self.get_log_stats()` to obtain base statistics (`total`, `chat_requests`, `guardrail_incidents`, `system_errors`).
2. Call `self.log_repo.aggregate_token_stats()` to obtain aggregated data (`total_tokens`, `avg_latency_ms`).
3. Merge both dicts into one and return the result with keys: `total`, `chat_requests`, `guardrail_incidents`, `system_errors`, `total_tokens`, `avg_latency_ms`.

### Data Consistency (Race Condition)

The method executes two separate DB queries without a single transaction. New records may be inserted between calls, leading to minor data inconsistency. This is acceptable for a dashboard since the data is informational and refreshes on the next request.

### Error Handling

- If `aggregate_token_stats()` raises an exception — log the error at WARNING level and return `total_tokens` = 0, `avg_latency_ms` = 0.0 (graceful degradation). Base statistics are returned normally.

---

## 10. Method: get_chart_data

### Purpose

Retrieve data for the activity chart — event counts by hour.

### Interface Description

- **Async method** accepting one parameter: `hours` (integer, default 24).
- **Returns:** list of dicts with keys `hour` and `count`.

### Algorithm

1. Compute the timestamp `since` = current UTC time minus `hours` hours.
2. Call `self.log_repo.count_by_hour(since=since)`.
3. Convert the list of tuples (hour_string, count) into a list of dicts with keys `hour` and `count`.
4. Return the result.

### Error Handling

- Repository exceptions are propagated upstream (handled by the router).

---

## 11. Method: get_log_by_id

### Purpose

Retrieve a single log record by numeric ID. Required for the POST /api/logs/{id}/replay endpoint.

### Interface Description

- **Async method** accepting one parameter: `log_id` (integer).
- **Returns:** LogEntryModel instance or None.

### Algorithm

1. Call `self.log_repo.get_by_id(log_id)`.
2. Return the result.

---

## 12. Method: export_logs

### Purpose

Generate CSV data for log export. Returns an async generator of CSV strings.

### Interface Description

- **Async generator** accepting two parameters:
  - `event_type` (string or None) — filter by event type.
  - `limit` (integer, default 10000) — maximum number of records.
- **Yield:** CSV strings (including header).

### Algorithm

1. Log an audit event at INFO level: "CSV export started", specifying event_type, limit. Caller user information is passed from the router (if available).
2. Initialize an exported records counter (for the audit log).
3. Yield the CSV header string: "id,trace_id,event_type,created_at,payload\n".
4. Call `self.log_repo.list_for_export(event_type=event_type, limit=limit)`.
5. For each record in the result:
   a. Build a CSV string with fields: `id`, `trace_id`, `event_type`, `created_at` (in ISO 8601 format), `payload` (JSON string, escaped for CSV — wrap in double quotes, double internal double quotes).
   b. **CSV Injection protection**: before writing the payload value to CSV, check if the string value starts with characters `=`, `+`, `-`, `@`, `\t`, `\r`. If so — prepend a single quote prefix to prevent formula execution when opened in Excel.
   c. Increment the counter.
   d. Yield the built string.
6. Upon iteration completion — log an audit event at INFO level: "CSV export completed", specifying the number of exported records.

### Error Handling (Streaming Error Handling)

- If the repository query or record iteration raises an exception AFTER generation has started (HTTP headers already sent to client) — yield an error marker string: `# ERROR: export interrupted\n`. This allows the client to detect an incomplete export. Then log the error at ERROR level and terminate the generator.
- If the exception occurs BEFORE the first yield — propagate the exception upstream (router returns HTTP 500).

### Security and PII

- CSV export includes the full `payload`, which may contain user prompts and LLM responses (PII/confidential data).
- Every export call MUST be logged as an audit event (who called, when, how many records exported).
- Export access is restricted by authentication (HTTP Basic Auth at the router level).
- Payload values are escaped for CSV Injection protection.

---

## 13. Error Handling

| Scenario                        | Action                                            |
|---------------------------------|---------------------------------------------------|
| DB error on log write           | Suppress, output to stderr via `logging.error`    |
| DB error on log read            | Propagate upstream (for UI display)               |
| Invalid payload                 | Write as-is (Text field accepts any JSON)         |
| aggregate_token_stats error     | WARNING log, graceful degradation (zeros)         |
| Streaming export error          | Yield error marker, ERROR log, terminate generator|
