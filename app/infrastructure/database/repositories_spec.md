# Спецификация: Репозитории — CRUD-операции (repositories.py)

> **Файл реализации:** `repositories.py`  
> **Слой:** Infrastructure (внешний мир — I/O)  
> **Ответственность:** Инкапсуляция всех SQL-запросов. Сервисный слой работает с репозиториями, а не с ORM напрямую.

---

## 1. Общие правила

- Все операции с БД — **асинхронные** (через AsyncSession).
- Репозитории принимают AsyncSession как зависимость (Dependency Injection).
- ORM-модели SQLAlchemy **не экспортируются** за пределы слоя infrastructure.
- Все методы — async.
- Сериализация body/payload (dict → JSON-строка) происходит **внутри** репозитория.
- Десериализация (JSON-строка → dict) происходит **внутри** репозитория.
- При ошибках БД — пробрасывается SQLAlchemyError (обработка — на уровне сервисов).
- soft_delete устанавливает is_active=False и updated_at=utcnow().

---

## 2. Класс: ProviderRepository

**Зависимость:** AsyncSession (через конструктор).

| Метод                                          | Возвращает              | Описание                                    |
|------------------------------------------------|-------------------------|---------------------------------------------|
| get_active_by_name(name: str)                  | ProviderModel или None  | Найти активного провайдера по имени          |
| get_by_id(provider_id: int)                    | ProviderModel или None  | Найти провайдера по ID                       |
| list_all(only_active: bool = True)             | список ProviderModel    | Список всех (или только активных) провайдеров|
| create(name, api_key, base_url)                | ProviderModel           | Создать нового провайдера                    |
| update(provider_id, **fields)                  | ProviderModel или None  | Обновить поля провайдера                     |
| soft_delete(provider_id: int)                  | bool                    | Пометить как неактивного (is_active=False)   |

---

## 3. Класс: PolicyRepository

**Зависимость:** AsyncSession (через конструктор).

| Метод                                          | Возвращает              | Описание                                    |
|------------------------------------------------|-------------------------|---------------------------------------------|
| get_by_id(policy_id: int)                      | PolicyModel или None    | Найти политику по ID                         |
| get_by_remote_id(remote_id: str)               | PolicyModel или None    | Найти политику по remote_id вендора          |
| list_all(only_active: bool = True)             | список PolicyModel      | Список всех (или только активных) политик    |
| list_by_provider(provider_id: int)             | список PolicyModel      | Политики конкретного провайдера              |
| create(name, body, remote_id, provider_id)     | PolicyModel             | Создать новую политику                       |
| update(policy_id, **fields)                    | PolicyModel или None    | Обновить поля политики                       |
| soft_delete(policy_id: int)                    | bool                    | Пометить как неактивную (is_active=False)    |
| upsert_by_remote_id(remote_id, name, body, provider_id) | PolicyModel  | Создать или обновить по remote_id (для синхронизации) |

---

## 4. Класс: LogRepository

**Зависимость:** AsyncSession (через конструктор).

| Метод                                          | Возвращает              | Описание                                    |
|------------------------------------------------|-------------------------|---------------------------------------------|
| create(trace_id, event_type, payload)          | LogEntryModel           | Записать новое событие в журнал              |
| get_by_trace_id(trace_id: str)                 | список LogEntryModel    | Все события по trace_id (промпт + инциденты) |
| list_all(limit: int = 100, offset: int = 0)    | список LogEntryModel    | Постраничный список всех событий             |
| list_by_type(event_type: str, limit, offset)   | список LogEntryModel    | Фильтрация по типу события                  |
| count_all()                                    | int                     | Общее количество записей                     |
| count_by_type(event_type: str)                 | int                     | Количество записей определённого типа        |

---

## 5. Обработка ошибок

| Ситуация                        | Действие                                    |
|---------------------------------|---------------------------------------------|
| Дубликат UNIQUE-поля            | IntegrityError → пробрасывается в сервис    |
| Запись не найдена               | Возвращается None                           |
| Ошибка подключения к БД         | OperationalError → логирование + re-raise   |
| Невалидный JSON при сериализации| ValueError → пробрасывается в сервис        |
