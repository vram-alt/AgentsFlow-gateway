# Спецификация: Dependencies (Внедрение зависимостей)

> **Файл реализации:** `di.py`  
> **Слой:** API / Delivery  
> **Ответственность:** Фабрики зависимостей для FastAPI Depends — сборка сервисов, репозиториев, адаптеров

---

## 1. Общие правила

- Все зависимости создаются через функции-фабрики для FastAPI `Depends`.
- Каждая фабрика получает `AsyncSession` из `get_db_session()` и собирает граф зависимостей.
- Адаптер провайдера создаётся как синглтон на уровне модуля (stateless).
- Фабрики **не содержат** бизнес-логики.

---

## 2. Модуль: di.py

### 2.1. Фабрика: get_provider_repo

- **Зависимости:** AsyncSession (из get_db_session)
- **Возвращает:** ProviderRepository
- **Логика:** Создаёт экземпляр ProviderRepository, передавая ему текущую сессию БД.

### 2.2. Фабрика: get_policy_repo

- **Зависимости:** AsyncSession (из get_db_session)
- **Возвращает:** PolicyRepository
- **Логика:** Создаёт экземпляр PolicyRepository, передавая ему текущую сессию БД.

### 2.3. Фабрика: get_log_repo

- **Зависимости:** AsyncSession (из get_db_session)
- **Возвращает:** LogRepository
- **Логика:** Создаёт экземпляр LogRepository, передавая ему текущую сессию БД.

### 2.4. Фабрика: get_adapter

- **Зависимости:** нет (stateless)
- **Возвращает:** GatewayProvider (конкретно — PortkeyAdapter)
- **Логика:** Возвращает экземпляр PortkeyAdapter. Поскольку адаптер не хранит состояния, допускается переиспользование одного экземпляра.

### 2.5. Фабрика: get_log_service

- **Зависимости:** LogRepository (из get_log_repo)
- **Возвращает:** LogService
- **Логика:** Создаёт экземпляр LogService, передавая ему LogRepository.

### 2.6. Фабрика: get_chat_service

- **Зависимости:** ProviderRepository (из get_provider_repo), LogService (из get_log_service), GatewayProvider (из get_adapter)
- **Возвращает:** ChatService
- **Логика:** Создаёт экземпляр ChatService, передавая ему все три зависимости.

### 2.7. Фабрика: get_policy_service

- **Зависимости:** PolicyRepository (из get_policy_repo), ProviderRepository (из get_provider_repo), LogService (из get_log_service), GatewayProvider (из get_adapter)
- **Возвращает:** PolicyService
- **Логика:** Создаёт экземпляр PolicyService, передавая ему все четыре зависимости.

### 2.8. Фабрика: get_webhook_service

- **Зависимости:** LogService (из get_log_service), LogRepository (из get_log_repo)
- **Возвращает:** WebhookService
- **Логика:** Создаёт экземпляр WebhookService, передавая ему LogService и LogRepository.

### 2.9. Фабрика: get_http_client

- **Зависимости:** GatewayProvider (из get_adapter)
- **Возвращает:** httpx.AsyncClient
- **Логика:**
  1. Получить синглтон адаптера через существующую фабрику `get_adapter()`.
  2. **Проверка готовности**: если адаптер равен None (не инициализирован, race condition при startup) — вернуть HTTP 503 с телом "Service not ready". Это предотвращает `AttributeError` при обращении к неинициализированному адаптеру.
  3. Вызвать **публичный** метод `get_http_client()` (без префикса `_`) адаптера для получения переиспользуемого httpx-клиента. Приватный метод `_get_http_client()` НЕ должен вызываться из DI-фабрики — это нарушение инкапсуляции. Публичный метод должен быть добавлен в `PortkeyAdapter` (или в контракт `GatewayProvider`), делегирующий вызов к приватному.
  4. Вернуть клиент.
- **Обоснование:** Переиспользование HTTP-клиента из адаптера позволяет не создавать дополнительный пул соединений для health-check, использовать единый таймаут из настроек приложения и корректно закрывать клиент при shutdown (уже реализовано в lifespan).

### 2.10. Фабрика: get_tester_http_client

- **Зависимости:** GatewayProvider (из get_adapter)
- **Возвращает:** httpx.AsyncClient (изолированный экземпляр)
- **Логика:**
  1. Получить синглтон адаптера через существующую фабрику `get_adapter()`.
  2. **Проверка готовности**: если адаптер равен None — вернуть HTTP 503 с телом "Service not ready".
  3. Вернуть изолированный HTTP-клиент для тестера. Клиент создаётся как модульный синглтон (lazy initialization) с собственным пулом соединений (максимум 10 соединений). Таймаут берётся из настроек приложения.
  4. Клиент ДОЛЖЕН корректно закрываться при shutdown приложения. Добавить закрытие в lifespan или использовать финализатор.
- **Обоснование изоляции:** Переиспользование единого `httpx.AsyncClient` из адаптера для TesterService и health-check создаёт shared state. Если TesterService отправляет тяжёлый запрос с большим body, это может исчерпать connection pool для health-check и наоборот. Изолированный клиент с собственным пулом соединений предотвращает каскадные отказы.
- **Жизненный цикл:** Клиент создаётся при первом вызове фабрики (lazy), переиспользуется между запросами (синглтон на уровне модуля), закрывается при shutdown приложения (через lifespan или atexit).

### 2.11. Фабрика: get_tester_service

- **Зависимости:** ProviderRepository (из get_provider_repo), httpx.AsyncClient (из get_tester_http_client)
- **Возвращает:** TesterService
- **Логика:**
  1. Получить `provider_repo` через DI (Depends на `get_provider_repo`).
  2. Получить `http_client` через DI (Depends на `get_tester_http_client`).
  3. Создать и вернуть экземпляр `TesterService(provider_repo=provider_repo, http_client=http_client)`.
- **Защитная проверка:** Если `provider_repo` не является экземпляром `ProviderRepository` — создать fallback с `session=None` (аналогично существующим фабрикам).

---

## 3. Граф зависимостей

Корневая зависимость — AsyncSession (из get_db_session). От неё ответвляются:

- **ProviderRepository** → используется в ChatService, PolicyService и TesterService.
- **PolicyRepository** → используется в PolicyService.
- **LogRepository** → используется в LogService и WebhookService. LogService, в свою очередь, используется в ChatService, PolicyService и WebhookService.
- **PortkeyAdapter** (stateless-синглтон, без зависимости от сессии) → используется в ChatService, PolicyService, get_http_client и get_tester_http_client.
- **httpx.AsyncClient (основной)** → используется в ProviderService (health-check).
- **httpx.AsyncClient (изолированный)** → используется в TesterService.

---

## 4. Обработка ошибок

- Ошибки создания зависимостей (например, недоступна БД) пробрасываются как HTTP 500.
- FastAPI автоматически обрабатывает исключения из `Depends`-функций.
- Если адаптер не инициализирован при вызове `get_http_client` или `get_tester_http_client` — HTTP 503 "Service not ready".
