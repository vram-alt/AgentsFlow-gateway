# Полный список реализованных эндпоинтов AI Gateway POC

Все роутеры подключены в `app/main.py` через `include_router`. Плюс один эндпоинт зарегистрирован напрямую на объекте `app`.

## 🏥 Health (напрямую на `app`)

*   `GET /health` — Простой health-check для Docker HEALTHCHECK и мониторинга. Возвращает `{"status": "ok"}`. Auth: ❌ Нет. Файл: `app/main.py`.

## 💬 Chat (`/api/chat`)

*   `POST /api/chat/send` — Отправка промпта к LLM через шлюз (Режим А). Принимает модель, сообщения, провайдер, temperature, max_tokens, guardrail_ids. Возвращает ответ LLM или GatewayError. Auth: ✅ Bearer. Файл: `app/api/routes/chat.py`.

## 📜 Logs (`/api/logs`)

*   `GET /api/logs/` — Постраничный список событий журнала. Параметры: `limit`, `offset`, `event_type`, `trace_id`. Если `trace_id` передан — возвращает все события по этому trace. Auth: ✅ Bearer. Файл: `app/api/routes/logs.py`.
*   `GET /api/logs/stats` — Статистика событий для дашборда (агрегация по типам). Auth: ✅ Bearer. Файл: `app/api/routes/logs.py`.
*   `GET /api/logs/export` — CSV-экспорт логов. Параметры: `event_type`, `limit` (до 50000). Возвращает `StreamingResponse` с файлом `logs_export.csv`. Auth: ✅ Bearer. Файл: `app/api/routes/logs.py`.
*   `POST /api/logs/{log_id}/replay` — Повтор чат-запроса из лога. Извлекает параметры из payload оригинального лога и повторно вызывает ChatService. Rate-limit: 10 запросов/мин на пользователя. Auth: ✅ Bearer. Файл: `app/api/routes/logs.py`.
*   `GET /api/logs/{trace_id}` — Все события по конкретному `trace_id` (path-параметр). Auth: ✅ Bearer. Файл: `app/api/routes/logs.py`.

## 🛡️ Policies (`/api/policies`)

*   `GET /api/policies/` — Список всех активных политик безопасности (guardrails). Auth: ✅ Bearer. Файл: `app/api/routes/policies.py`.
*   `POST /api/policies/` — Создание новой политики. Тело: `name`, `body`, `provider_name`. Возвращает 201. Auth: ✅ Bearer. Файл: `app/api/routes/policies.py`.
*   `POST /api/policies/sync` — Синхронизация политик из облачного провайдера. Тело: `provider_name`. Auth: ✅ Bearer. Файл: `app/api/routes/policies.py`.
*   `PUT /api/policies/{policy_id}` — Обновление политики. Тело: `name`, `body`. Auth: ✅ Bearer. Файл: `app/api/routes/policies.py`.
*   `DELETE /api/policies/{policy_id}` — Мягкое удаление политики (soft delete). Auth: ✅ Bearer. Файл: `app/api/routes/policies.py`.

## 🔌 Providers (`/api/providers`)

*   `GET /api/providers/health` — Проверка доступности провайдеров (health-check). Кэш 30 сек. Использует httpx-клиент для пинга. Auth: ✅ Bearer. Файл: `app/api/routes/providers.py`.
*   `GET /api/providers/` — Список всех LLM-провайдеров. Auth: ✅ Bearer. Файл: `app/api/routes/providers.py`.
*   `POST /api/providers/` — Создание нового провайдера. Тело: `name`, `api_key`, `base_url`. Возвращает 201. Auth: ✅ Bearer. Файл: `app/api/routes/providers.py`.
*   `PUT /api/providers/{provider_id}` — Обновление провайдера. Тело: `name`, `api_key`, `base_url`. Auth: ✅ Bearer. Файл: `app/api/routes/providers.py`.
*   `DELETE /api/providers/{provider_id}` — Мягкое удаление провайдера (soft delete). Auth: ✅ Bearer. Файл: `app/api/routes/providers.py`.

## 📊 Stats (`/api/stats`)

*   `GET /api/stats/summary` — Сводная статистика для дашборда. Кэш 60 сек с async-lock (double-check pattern). Auth: ✅ Bearer. Файл: `app/api/routes/stats.py`.
*   `GET /api/stats/charts` — Данные для графиков. Параметр: `hours` (1–168, по умолчанию 24). Auth: ✅ Bearer. Файл: `app/api/routes/stats.py`.

## 🧪 Tester (`/api/tester`)

*   `GET /api/tester/schema` — Статическая JSON-схема формы Testing Console (поля: provider, model, prompt, temperature, max_tokens). Auth: ✅ Bearer. Файл: `app/api/routes/tester.py`.
*   `POST /api/tester/proxy` — Прокси-запрос к провайдеру. Тело: `provider_name`, `method`, `path`, `body`, `headers`. Auth: ✅ Bearer. Файл: `app/api/routes/tester.py`.

## 🔔 Webhook (`/api/webhook`)

*   `POST /api/webhook` — Приём входящих webhook-отчётов от провайдеров. Валидация: HMAC-сравнение секрета, лимит payload 1MB, макс. вложенность JSON = 10. Передаёт payload в `WebhookService.process_guardrail_incident()`. Auth: 🔑 `X-Webhook-Secret`. Файл: `app/api/routes/webhook.py`.

---

### 📈 Сводка

| Модуль | Кол-во эндпоинтов | Методы |
| :--- | :--- | :--- |
| Health | 1 | GET |
| Chat | 1 | POST |
| Logs | 5 | GET(3), POST(1), GET(1) |
| Policies | 5 | GET, POST(2), PUT, DELETE |
| Providers | 5 | GET(2), POST, PUT, DELETE |
| Stats | 2 | GET(2) |
| Tester | 2 | GET, POST |
| Webhook | 1 | POST |
| **ИТОГО** | **22** | |
