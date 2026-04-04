# Specification: Repositories — CRUD Operations (repositories.py)

> **Implementation file:** `repositories.py`  
> **Layer:** Infrastructure (external world — I/O)  
> **Responsibility:** Encapsulating all SQL queries. The service layer works with repositories, not with ORM directly.

---

## 1. General Rules

- All DB operations are **asynchronous** (via AsyncSession).
- Repositories accept AsyncSession as a dependency (Dependency Injection).
- SQLAlchemy ORM models are **not exported** beyond the infrastructure layer.
- All methods are async.
- Serialization of body/payload (dict → JSON string) occurs **within** the repository.
- Deserialization (JSON string → dict) occurs **within** the repository.
- On DB errors — SQLAlchemyError is propagated (handling is at the service level).
- soft_delete sets is_active=False and updated_at=utcnow().

---

## 2. Class: ProviderRepository

**Dependency:** AsyncSession (via constructor).

| Method                                         | Returns                 | Description                                 |
|------------------------------------------------|-------------------------|---------------------------------------------|
| get_active_by_name(name: str)                  | ProviderModel or None   | Find an active provider by name             |
| get_by_id(provider_id: int)                    | ProviderModel or None   | Find a provider by ID                       |
| list_all(only_active: bool = True)             | list of ProviderModel   | List all (or only active) providers         |
| create(name, api_key, base_url)                | ProviderModel           | Create a new provider                       |
| update(provider_id, **fields)                  | ProviderModel or None   | Update provider fields                      |
| soft_delete(provider_id: int)                  | bool                    | Mark as inactive (is_active=False)          |

---

## 3. Class: PolicyRepository

**Dependency:** AsyncSession (via constructor).

| Method                                         | Returns                 | Description                                 |
|------------------------------------------------|-------------------------|---------------------------------------------|
| get_by_id(policy_id: int)                      | PolicyModel or None     | Find a policy by ID                         |
| get_by_remote_id(remote_id: str)               | PolicyModel or None     | Find a policy by vendor remote_id           |
| list_all(only_active: bool = True)             | list of PolicyModel     | List all (or only active) policies          |
| list_by_provider(provider_id: int)             | list of PolicyModel     | Policies for a specific provider            |
| create(name, body, remote_id, provider_id)     | PolicyModel             | Create a new policy                         |
| update(policy_id, **fields)                    | PolicyModel or None     | Update policy fields                        |
| soft_delete(policy_id: int)                    | bool                    | Mark as inactive (is_active=False)          |
| upsert_by_remote_id(remote_id, name, body, provider_id) | PolicyModel  | Create or update by remote_id (for sync)    |

---

## 4. Class: LogRepository

**Dependency:** AsyncSession (via constructor).

### 4.1. Existing Methods

| Method                                         | Returns                 | Description                                 |
|------------------------------------------------|-------------------------|---------------------------------------------|
| create(trace_id, event_type, payload)          | LogEntryModel           | Write a new event to the audit log          |
| get_by_trace_id(trace_id: str)                 | list of LogEntryModel   | All events by trace_id (prompt + incidents) |
| list_all(limit: int = 100, offset: int = 0)    | list of LogEntryModel   | Paginated list of all events                |
| list_by_type(event_type: str, limit, offset)   | list of LogEntryModel   | Filter by event type                        |
| count_all()                                    | int                     | Total record count                          |
| count_by_type(event_type: str)                 | int                     | Record count for a specific type            |

### 4.2. Method: get_by_id

- **Purpose:** Retrieve a single log record by numeric primary key (id). Required for the POST /api/logs/{id}/replay endpoint.
- **Parameters:** `log_id` — integer, record primary key.
- **Returns:** `LogEntryModel` instance or None (if record not found).
- **Algorithm:** Execute a SELECT SQL query on the `logs` table with a filter on the `id` column equal to the provided `log_id`. Return the single result or None.

### 4.3. Method: count_by_hour

- **Purpose:** Group log records by hourly intervals for building an activity chart. Required for the GET /api/stats/charts endpoint.
- **Parameters:** `since` — datetime object (timezone-aware, UTC), start of the time range.
- **Returns:** list of tuples (hour_string, count), where `hour_string` is a string in "YYYY-MM-DD HH:00" format, `count` is an integer.
- **Algorithm:**
  1. Execute a SQL query on the `logs` table: filter `created_at` >= `since`, group by the result of formatting `created_at` into a "YYYY-MM-DD HH:00" string via a private helper function `_format_hour(column)`, aggregate COUNT per group, sort by hour string in ascending order.
  2. Return the list of tuples.
- **DBMS Compatibility (DB Portability):** Date formatting MUST be extracted into a separate private helper function `_format_hour(column)`. This function determines the current DBMS dialect via the session dialect property and returns: for SQLite — a SQL expression via the `strftime` function; for PostgreSQL — a SQL expression via the `date_trunc` function.
- **Index Requirement (Performance):** Add an Alembic migration creating an index on the `logs.created_at` column (index name: `ix_logs_created_at`), if the index does not already exist. The migration must be idempotent.

### 4.4. Method: aggregate_token_stats

- **Purpose:** Aggregate token and latency statistics from the JSON `payload` field of all records. Required for the GET /api/stats/summary endpoint.
- **Parameters:** none.
- **Returns:** dict with keys `total_tokens` (integer) and `avg_latency_ms` (float).
- **Algorithm:**
  1. Execute a SQL query on the `logs` table, extracting ONLY the `id` and `payload` columns for records with `event_type` = "chat_request". Loading all columns is prohibited to conserve memory.
  2. Use streaming result processing (server-side cursor with batch fetching of 500 records at a time) instead of loading all records into memory in a single query.
  3. JSON parsing from the `payload` field is a CPU-bound operation. To prevent event-loop blocking with a large number of records — perform parsing in a separate thread (via executor or similar mechanism).
  4. For each record: parse `payload` from JSON string to dict (on parse error — log the record `id` at WARNING level with message "Corrupted payload in log entry" and skip the record); attempt to extract `response.usage.total_tokens` (if numeric — add to sum); attempt to extract `response.latency_ms` (if numeric — add to latency list).
  5. Compute: `total_tokens` = sum of all tokens; `avg_latency_ms` = arithmetic mean of latency, rounded to 2 decimal places (if list is empty — 0.0).
  6. Return the dict.
- **Optimization:** JSON parsing in Python (rather than via SQL JSON functions) is a deliberate choice: SQLite does not have built-in JSON functions in the standard aiosqlite distribution; data volume at the POC stage is small. When scaling to PostgreSQL, `jsonb` operators can be used. Measures: load only `id` and `payload`; filter by `event_type` = "chat_request"; stream processing in batches of 500; CPU-bound parsing in a separate thread.

### 4.5. Method: list_for_export

- **Purpose:** Retrieve log records for CSV export with optional event type filtering. Required for the GET /api/logs/export endpoint.
- **Type:** Async generator.
- **Parameters:** `event_type` (string or None), `limit` (integer, default 5000).
- **Yield:** `LogEntryModel` instances (streaming).
- **Algorithm:**
  1. Build a SELECT SQL query on the `logs` table.
  2. If `event_type` is not None — add a filter on the `event_type` column.
  3. Add sorting by `created_at` in descending order (newest records first).
  4. Add LIMIT equal to the provided `limit`.
  5. Execute the query using streaming (server-side cursor with batch fetching of 1000 records at a time).
  6. Yield each record as it is received from the stream.
- **Default limit value:** Reduced to 5000 to limit memory consumption. At ~5KB per payload, this is ~25MB — an acceptable volume.

---

## 5. Error Handling

| Scenario                        | Action                                      |
|---------------------------------|---------------------------------------------|
| UNIQUE field duplicate          | IntegrityError → propagated to service      |
| Record not found                | Returns None                                |
| DB connection error             | OperationalError → logging + re-raise       |
| Invalid JSON on serialization   | ValueError → propagated to service          |
| Corrupted JSON in payload       | WARNING log with record id, record skipped  |
