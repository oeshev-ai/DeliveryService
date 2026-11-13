# Delivery Service Chatbot

[![CI](https://github.com/oeshev-ai/DeliveryService/actions/workflows/ci.yml/badge.svg)](https://github.com/oeshev-ai/DeliveryService/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)

Клиентский Telegram-бот поддержки сервиса доставки: статус заказа, курьер/карта,
смена адреса и времени, отмена с возвратом, FAQ, претензии/отзывы, эскалация к оператору.
Стек: **Python 3.12 · aiogram 3 · FastAPI · SQLAlchemy 2 (async) · PostgreSQL · Redis · ARQ**.

OMS / TMS / Payments / CRM — **моки** (так и задумано для портфолио и локального демо).

## Архитектура

```mermaid
flowchart LR
  subgraph Clients
    TG[Telegram]
    MA[Mini App]
  end

  subgraph Runtime
    BOT[bot<br/>aiogram + health :8081]
    API[api<br/>FastAPI :8000]
    WRK[worker<br/>ARQ]
  end

  subgraph Data
    PG[(PostgreSQL)]
    RD[(Redis)]
  end

  TG --> BOT
  MA --> API
  BOT --> API
  BOT --> RD
  API --> PG
  API --> RD
  WRK --> PG
  WRK --> RD
  WRK --> TG
```

| Сервис | Роль |
|--------|------|
| `bot` | Telegram polling, FSM/сессии, health/metrics на `${HOST_BOT_HEALTH_PORT:-18081}` |
| `api` | Mock OMS/TMS/CRM/FAQ + WebApp UI на `${HOST_API_PORT:-18000}`; перед стартом `alembic upgrade head` |
| `worker` | Напоминания об отзыве, доставка ответов оператора |
| `postgres` / `redis` | Только внутри Docker-сети (на хост не публикуются) |

## Скриншоты

Добавьте PNG в `docs/screenshots/` (имена ниже — контракт README):

| Файл | Содержание |
|------|------------|
| `docs/screenshots/bot-menu.png` | Главное меню бота |
| `docs/screenshots/webapp-status.png` | Mini App — вкладка статуса |
| `docs/screenshots/webapp-map.png` | Mini App — карта курьера |
| `docs/screenshots/webapp-history.png` | Mini App — история заказов |

<!-- placeholders до появления файлов -->
![Бот — меню](docs/screenshots/bot-menu.png)
![Mini App — статус](docs/screenshots/webapp-status.png)
![Mini App — карта](docs/screenshots/webapp-map.png)
![Mini App — история](docs/screenshots/webapp-history.png)

## Быстрый старт (Docker)

```bash
cp .env.example .env
# TELEGRAM_BOT_TOKEN=...  (обязательно сменить секреты перед production)

docker compose up --build
```

```bash
curl http://localhost:18081/health
curl http://localhost:18000/health
```

Compose-проект: `name: delivery`. Порты на хосте — `HOST_API_PORT` / `HOST_BOT_HEALTH_PORT`.
Для Mini App с телефона нужен HTTPS (`TELEGRAM_WEBAPP_URL`).

## Локальная разработка

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
# DATABASE_URL / REDIS_URL на локальные сервисы
alembic upgrade head
python -m delivery_bot
# API: uvicorn delivery_bot.api.app:app --reload
```

## Миграции

```bash
alembic upgrade head          # применить
alembic downgrade -1          # откатить одну
alembic revision --autogenerate -m "describe_change"
```

**Legacy-БД** (раньше через `create_all`): `python scripts/stamp_legacy_db.py`, затем обычные upgrade для новых ревизий.

## Тесты

```bash
pip install -e ".[dev]"

# Unit-тесты — fakeredis / AsyncMock.
# Интеграционные (CRM, concurrency reviews, history SQL) — нужен PostgreSQL:
export DATABASE_URL=postgresql+asyncpg://delivery:delivery_secret@localhost:5432/delivery
export APP_ENV=test
pytest --cov=delivery_bot --cov-report=term-missing
```

PowerShell (часто удобнее порт `15432`, если `:5432` занят Hyper-V):

```powershell
docker run --rm -d --name delivery-pg-test `
  -e POSTGRES_DB=delivery -e POSTGRES_USER=delivery -e POSTGRES_PASSWORD=delivery_secret `
  -p 15432:5432 postgres:16-alpine
$env:DATABASE_URL = "postgresql+asyncpg://delivery:delivery_secret@localhost:15432/delivery"
$env:APP_ENV = "test"
pytest
```

CI (`ci.yml`): lint (ruff) → mypy → pytest + Postgres 16 service container.

## Возможности

- Согласие на ПДн, FSM в Redis (TTL 30 мин), AttemptLimiter на верификацию
- Статус заказа (verify order_id + last4), кэш OMS 90 с, graceful degradation
- Mini App: статус / карта OSM / история; `WEBAPP_DEV_BYPASS` только для local
- Смена адреса/слота, полная и частичная отмена + mock refund
- FAQ (+ опциональный LLM), претензии, отзывы, reorder, CRM handoff
- PII-маскирование в structlog, Prometheus `/metrics`, `X-Request-ID`

Демо-заказы: `ORD-1001`…`ORD-1006`, телефон `+79001234567` (last4=`4567`).

## Архитектурные решения и компромиссы

**Моки интеграций.** Реальный OMS/платёжный шлюз/CRM недоступны в учебном контуре.
Контракты (`/oms/v1`, `/crm/v1`, payments gateway) стабильны: подмена клиента не ломает бота и WebApp.
Это осознанный trade-off: глубина сценариев важнее «настоящих» HTTP-вызовов.

**Атомарный AttemptLimiter (Lua).** Раньше `TTL → INCR → EXPIRE → SET block → DEL` гонялись
между процессами. Теперь один Redis Lua-скрипт: ровно `max_attempts - 1` разрешённых
параллельных `hit()`, после блока счётчик удаляется вместе с TTL. `check()` остаётся
advisory; решение — только в `hit()`.

**Идемпотентность платежей (SET NX).** Payload — JSON `{payment_id, amount}` с TTL 24 ч.
Повтор с той же суммой возвращает сохранённый id; другая сумма → отказ
(«ключ идемпотентности уже использован с другой суммой»). Если ключ истёк между
`SET NX` и `GET` — одна повторная попытка.

**Лок диалоговой сессии.** Два быстрых апдейта Telegram затирали FSM (read-modify-write).
Лок `dialog:lock:{channel}:{user_id}`: `SET NX PX 10000` + uuid-токен, ожидание до 5 с,
освобождение compare-and-del (чужой лок не трогаем). При contention handler не вызывается —
пользователь видит «Обрабатываю ваше предыдущее сообщение, секунду…».

**Alembic вместо create_all в проде.** API поднимает схему через `alembic upgrade head`.
`init_db`/`create_all` оставлены для тестов. БД, созданные старым путём:
`scripts/stamp_legacy_db.py` → stamp `head`, дальше только новые ревизии.
В initial-миграции перед `uq_reviews_order_user` удаляются дубли отзывов.

**История заказов без N+1.** `list_full_by_last4` + `selectinload(items)` и один
`WHERE order_id IN (...)` по отзывам: ≤ 3 SQL на `/webapp/v1/history`.

**Graceful degradation OMS.** Статус читается из Redis-кэша; при недоступном OMS бот
отдаёт последнее известное состояние / публичный факт «в пути», не падая целиком.

**Production guard.** При `APP_ENV=production` Settings падает, если `API_KEY` /
`ADMIN_BASIC_PASSWORD` на дефолтах, пустой `TELEGRAM_BOT_TOKEN` или `WEBAPP_DEV_BYPASS=true`.

## Структура

```
src/delivery_bot/
  channels/      # Telegram + stubs
  handlers/      # aiogram handlers
  dialog/        # FSM, intents, AttemptLimiter, sessions
  middleware/    # session load + per-user lock
  services/      # бизнес-логика и order_policy
  integrations/  # OMS, TMS, Payments, CRM, FAQ, LLM
  api/           # FastAPI
  worker/        # ARQ
  webapp/        # auth Mini App, bindings
  security/      # PII masking
migrations/      # Alembic (async)
webapp/static/   # Mini App UI
```
