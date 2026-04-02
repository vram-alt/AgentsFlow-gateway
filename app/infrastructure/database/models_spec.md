# Спецификация: ORM-модели SQLAlchemy (models.py)

> **Файл реализации:** `models.py`  
> **Слой:** Infrastructure (внешний мир — I/O)  
> **Ответственность:** Определение таблиц БД через декларативные ORM-модели SQLAlchemy 2.0

---

## 1. Общие правила

- Все операции с БД — **асинхронные** (через AsyncSession).
- ORM-модели SQLAlchemy **не экспортируются** за пределы слоя infrastructure.
- Все модели наследуются от единого декларативного базового класса (стиль SQLAlchemy 2.0+).

---

## 2. Базовый класс

- Единый декларативный базовый класс для всех ORM-моделей (стиль SQLAlchemy 2.0+).
- Все модели наследуются от этого базового класса.

---

## 3. Таблица: ProviderModel

**Имя таблицы:** `providers`

| Колонка      | Тип SQLAlchemy         | Ограничения                    | Описание                        |
|--------------|------------------------|--------------------------------|---------------------------------|
| `id`         | `Integer`              | PK, autoincrement              | Первичный ключ                  |
| `name`       | `String(100)`          | NOT NULL, UNIQUE               | Название провайдера             |
| `api_key`    | `String(500)`          | NOT NULL                       | API-ключ (зашифрованный)        |
| `base_url`   | `String(500)`          | NOT NULL                       | Базовый URL API                 |
| `is_active`  | `Boolean`              | NOT NULL, default=True         | Флаг активности (Soft Delete)   |
| `created_at` | `DateTime`             | NOT NULL, default=utcnow       | Дата создания                   |
| `updated_at` | `DateTime`             | NOT NULL, default=utcnow, onupdate=utcnow | Дата обновления   |

**Шифрование колонки api_key:** Значение колонки api_key должно храниться в зашифрованном виде с использованием симметричного шифрования (алгоритм Fernet). Мастер-ключ шифрования читается из поля encryption_key класса Settings (переменная окружения ENCRYPTION_KEY, определена в config_spec.md). Механизм получения ключа в ORM-слое: импорт функции get_settings из модуля конфигурации. При записи в БД — значение шифруется, при чтении из БД — расшифровывается. Это предотвращает раскрытие всех API-ключей провайдеров при компрометации файла БД (SQLite) или SQL-инъекции.

**Связи:** policies → relationship к PolicyModel (one-to-many).

---

## 4. Таблица: PolicyModel

**Имя таблицы:** `policies`

| Колонка       | Тип SQLAlchemy         | Ограничения                    | Описание                        |
|---------------|------------------------|--------------------------------|---------------------------------|
| `id`          | `Integer`              | PK, autoincrement              | Первичный ключ                  |
| `name`        | `String(200)`          | NOT NULL                       | Название политики               |
| `body`        | `Text`                 | NOT NULL                       | JSON-тело правила (сериализованный dict) |
| `remote_id`   | `String(200)`          | NULLABLE, UNIQUE               | ID политики на стороне вендора  |
| `provider_id` | `Integer`              | FK → providers.id, ON DELETE SET NULL | Привязка к провайдеру    |
| `is_active`   | `Boolean`              | NOT NULL, default=True         | Флаг активности (Soft Delete)   |
| `created_at`  | `DateTime`             | NOT NULL, default=utcnow       | Дата создания                   |
| `updated_at`  | `DateTime`             | NOT NULL, default=utcnow, onupdate=utcnow | Дата обновления   |

**Примечание:** Поле body хранится как Text (JSON-строка). При миграции на PostgreSQL заменяется на JSONB.

---

## 5. Таблица: LogEntryModel

**Имя таблицы:** `logs`

| Колонка      | Тип SQLAlchemy         | Ограничения                    | Описание                        |
|--------------|------------------------|--------------------------------|---------------------------------|
| `id`         | `Integer`              | PK, autoincrement              | Первичный ключ                  |
| `trace_id`   | `String(36)`           | NOT NULL, INDEX                | UUID сквозного идентификатора   |
| `event_type` | `String(50)`           | NOT NULL                       | Тип события (Enum как строка)   |
| `payload`    | `Text`                 | NOT NULL                       | Полиморфное тело (JSON-строка)  |
| `created_at` | `DateTime`             | NOT NULL, default=utcnow       | Дата создания                   |

**Индексы:** ix_logs_trace_id на колонке trace_id для быстрого поиска по сквозному ID.

---

## 6. Обработка ошибок

| Ситуация                        | Действие                                    |
|---------------------------------|---------------------------------------------|
| Дубликат UNIQUE-поля            | IntegrityError → пробрасывается в сервис    |
| Невалидный JSON при сериализации| ValueError → пробрасывается в сервис        |
