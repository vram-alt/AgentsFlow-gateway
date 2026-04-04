# Specification: DTO UnifiedPrompt (unified_prompt.py)

> **Implementation file:** `unified_prompt.py`  
> **Layer:** Domain (pure core, zero external dependencies except Pydantic)  
> **Responsibility:** Standardized representation of a user request to an LLM provider

---

## 1. General Rules

- The DTO is an **immutable** (frozen) Pydantic model for transferring data between layers.
- Adapters are required to transform vendor-specific formats into this DTO and back.
- The system core works **exclusively** with this DTO, never with vendor formats.
- The model must be configured as immutable (frozen) via the Pydantic V2 configuration mechanism.

---

## 2. Nested Model: MessageItem

| Field     | Type   | Required | Description                                 |
|-----------|--------|----------|---------------------------------------------|
| `role`    | string | Yes      | Role: "system", "user", "assistant"         |
| `content` | string | Yes      | Message text                                |

### MessageItem Validation

- `role`: strictly one of "system", "user", "assistant".

---

## 3. DTO: UnifiedPrompt

### Purpose

Standardized representation of a user request that the core passes to the adapter.

### Fields

| Field            | Type                 | Required | Default      | Description                                       |
|------------------|----------------------|----------|--------------|---------------------------------------------------|
| `trace_id`       | string               | Yes      | —            | UUID v4 request correlation identifier            |
| `model`          | string               | Yes      | —            | LLM model identifier (e.g., "gpt-4o")            |
| `messages`       | list of MessageItem  | Yes      | —            | List of conversation messages                     |
| `temperature`    | float or None        | No       | None         | Generation temperature (0.0–2.0)                  |
| `max_tokens`     | integer or None      | No       | None         | Maximum number of response tokens                 |
| `guardrail_ids`  | list of strings      | No       | empty list   | List of policy remote_ids to apply                |
| `metadata`       | dict                 | No       | empty dict   | Arbitrary metadata (passed to provider)           |

### Validation

- `trace_id`: UUID v4 format.
- `messages`: minimum 1 element in the list.
- `temperature`: if provided — in range [0.0, 2.0].
- `max_tokens`: if provided — positive integer.

---

## 4. Error Handling

A standard pydantic.ValidationError is raised on invalid data.
Transforming errors into HTTP responses is the responsibility of the api/ layer.
