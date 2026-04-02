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
└── ui/                # Jinja2 шаблоны, Bootstrap 5 статика
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

## Лицензия

Proprietary — Phase 3 POC.
