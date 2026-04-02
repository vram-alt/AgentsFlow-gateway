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

---

## 3. Граф зависимостей

Корневая зависимость — AsyncSession (из get_db_session). От неё ответвляются:

- **ProviderRepository** → используется в ChatService и PolicyService.
- **PolicyRepository** → используется в PolicyService.
- **LogRepository** → используется в LogService и WebhookService. LogService, в свою очередь, используется в ChatService, PolicyService и WebhookService.
- **PortkeyAdapter** (stateless-синглтон, без зависимости от сессии) → используется в ChatService и PolicyService.

---

## 4. Обработка ошибок

- Ошибки создания зависимостей (например, недоступна БД) пробрасываются как HTTP 500.
- FastAPI автоматически обрабатывает исключения из `Depends`-функций.
