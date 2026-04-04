# AI Gateway Adapter — Phase 3 POC

Легковесный асинхронный API-шлюз с веб-интерфейсом.  
Роль: интеллектуальный прокси между бизнес-логикой и LLM-провайдерами (Portkey).

## Архитектура

Проект построен по принципам **Clean Architecture** с паттерном **Adapter**:

```
app/
├── domain/            # Чистые сущности, DTO, контракты (0 внешних зависимостей)
├── services/          # Use Cases — оркестрация бизнес-логики
├── infrastructure/    # БД (SQLAlchemy Async), HTTP-адаптеры (Portkey)
├── api/               # FastAPI роутеры, middleware, DI
```

## Быстрый старт

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Стек

| Компонент       | Технология                        |
|-----------------|-----------------------------------|
| Backend         | FastAPI + Uvicorn                 |
| HTTP-клиент     | httpx (async)                     |
| БД              | SQLite (WAL) → PostgreSQL-ready   |
| ORM             | SQLAlchemy Async + aiosqlite      |
| Валидация       | Pydantic V2                       |

## Известные ограничения (POC)

### [RED-2] In-memory Rate Limiter — не работает в multi-worker среде

Текущая реализация rate limiter для защиты от brute-force атак использует
in-memory `dict` внутри каждого процесса. В multi-worker развёртывании
(например, `gunicorn -w 4 -k uvicorn.workers.UvicornWorker`) каждый воркер
поддерживает собственный независимый счётчик неудачных попыток.

**Последствия:** атакующий может распределить попытки между воркерами и
обойти лимит (вместо 5 попыток получит `5 × N_workers`).

**Рекомендация для продакшена:** заменить на Redis-backed sliding window
rate limiter (например, через `redis-py` + Lua-скрипт или библиотеку
`fastapi-limiter`).

Для текущего POC с одним воркером (`uvicorn --workers 1`) это ограничение
не является критичным.

## Лицензия

Proprietary — Phase 3 POC.
