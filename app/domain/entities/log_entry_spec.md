# Specification: Domain Entity LogEntry (log_entry.py)

> **Implementation file:** `log_entry.py`  
> **Layer:** Domain (pure core, zero external dependencies except Pydantic)  
> **Responsibility:** Describing the "Audit Log Entry" business entity — a unified polymorphic audit record

---

## 1. General Rules

- The model inherits from BaseModel (Pydantic).
- Uses Pydantic V2 (configuration via ConfigDict).
- Date fields have type datetime. The default value is set via a factory mechanism (default_factory) that retrieves the current UTC time **on each instance creation**, not once at module import. Use the timezone-aware variant for obtaining the current time (with explicit UTC timezone), as the timezone-naive variant is deprecated starting with Python 3.12.
- The model **does not contain** database logic — it is a pure domain object.

---

## 2. Enumeration: EventType

A string enumeration (inherits from str and Enum) with three allowed values:

| Constant Value         | String Representation      | Description                               |
|------------------------|----------------------------|-------------------------------------------|
| CHAT_REQUEST           | "chat_request"             | Prompt submission and LLM response event  |
| GUARDRAIL_INCIDENT     | "guardrail_incident"       | Guardrail trigger event                   |
| SYSTEM_ERROR           | "system_error"             | System error                              |

---

## 3. Entity: LogEntry

### Purpose

A unified polymorphic audit record. Stores chat events, Guardrail incidents, and system errors.

### Fields

| Field          | Type             | Required | Default          | Description                                   |
|----------------|------------------|----------|------------------|-----------------------------------------------|
| `id`           | int or None      | No       | None             | Primary key (assigned by DB)                  |
| `trace_id`     | string           | Yes      | —                | Correlation UUID (indexed)                    |
| `event_type`   | EventType        | Yes      | —                | Event type (Enum)                             |
| `payload`      | dict             | Yes      | —                | Polymorphic event body (JSON)                 |
| `created_at`   | datetime         | No       | current UTC time (via factory) | Record creation timestamp     |

### Validation

- `trace_id`: UUID v4 format (36 characters with hyphens).
- `event_type`: strictly one of the EventType Enum values.
- `payload`: non-empty dict.

---

## 4. Error Handling

The model raises a standard pydantic.ValidationError on invalid data.
No custom error handling is provided at the entity level — this is the responsibility of upstream layers (services, api).
