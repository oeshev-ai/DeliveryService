# Delivery Service Chatbot

[![CI](https://github.com/oeshev-ai/DeliveryService/actions/workflows/ci.yml/badge.svg)](https://github.com/oeshev-ai/DeliveryService/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)

Клиентский Telegram-бот для сервиса доставки (еда/товары).
MVP: aiogram + PostgreSQL + Redis + FastAPI (админка/WebApp backend) + моки OMS/TMS/Payments.

## Быстрый старт (Docker)

```bash
cp .env.example .env
# Укажите TELEGRAM_BOT_TOKEN в .env

docker compose up --build
```

Сервисы:
- `bot` — Telegram-бот + health на хосте `${HOST_BOT_HEALTH_PORT:-18081}`
- `api` — FastAPI + WebApp UI на `${HOST_API_PORT:-18000}`
- `postgres`, `redis` — **только внутри Docker-сети** (не публикуются на хост)
- `worker` — ARQ (напоминания отзывов, ответы оператора)

Локальная проверка здоровья:

```bash
curl http://localhost:18081/health
curl http://localhost:18000/health
```

### Запуск рядом с другими ботами на сервере

Compose-проект называется `delivery` (`name: delivery`) — контейнеры и volume не
пересекутся с чужими `docker compose` проектами.

Перед деплоем на сервере проверьте свободные порты:

```bash
ss -tlnp | grep -E ':(18000|18081|8000|8081|5432|6379)\s'
```

Если `18000`/`18081` заняты — в `.env` задайте другие `HOST_API_PORT` / `HOST_BOT_HEALTH_PORT`.

**Обязательно:**
1. Отдельный `TELEGRAM_BOT_TOKEN` (свой бот у BotFather) — один токен нельзя polling'ить дважды
2. Свой `.env` (не шарить `API_KEY` / пароли с другими ботами)
3. Для Mini App: `TELEGRAM_WEBAPP_URL=https://ваш-домен:порт/ui` (HTTPS)

Postgres и Redis этого стека наружу не торчат — конфликта с `:5432` / `:6379` других ботов нет.

## Локальная разработка без Docker (опционально)

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
pip install -e ".[dev]"
cp .env.example .env
# Поднимите postgres/redis или укажите локальные URL
python -m delivery_bot
```

## Миграции

Схема PostgreSQL управляется Alembic (`migrations/`). В Docker API при старте
выполняет `alembic upgrade head`.

```bash
# Применить все миграции
alembic upgrade head

# Откатить на одну ревизию
alembic downgrade -1

# Создать новую ревизию после изменения моделей
alembic revision --autogenerate -m "describe_change"
```

### Legacy-БД (раньше через ``create_all``)

Если таблицы уже созданы `init_db`/`create_all`, а `alembic_version` пуста:

```bash
python scripts/stamp_legacy_db.py
# далее обычные alembic upgrade head для новых ревизий
```

Скрипт stamp'ит `head` только если есть таблица `orders` и версия ещё не проставлена.

## Тесты

```bash
pip install -e ".[dev]"

# Большинство тестов — unit (fakeredis / AsyncMock), Postgres не нужен.
# Интеграционный тест CRM (tests/test_escalation.py::test_crm_repository_create_and_operator_reply)
# требует доступный PostgreSQL:
export DATABASE_URL=postgresql+asyncpg://delivery:delivery_secret@localhost:5432/delivery
export APP_ENV=test

pytest
# или с coverage:
pytest --cov=delivery_bot --cov-report=term-missing
```

На Windows (PowerShell):

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://delivery:delivery_secret@localhost:15432/delivery"
$env:APP_ENV = "test"
pytest
```

Локальный Postgres для интеграционного теста (порт 5432 на хосте часто занят Hyper-V — можно `15432`):

```bash
docker run --rm -d --name delivery-pg-test \
  -e POSTGRES_DB=delivery -e POSTGRES_USER=delivery -e POSTGRES_PASSWORD=delivery_secret \
  -p 15432:5432 postgres:16-alpine
```

## Структура

```
src/delivery_bot/
  channels/     # адаптеры каналов (Telegram + stubs)
  handlers/     # aiogram handlers
  dialog/       # Dialog Manager / FSM / intents / sessions
  middleware/   # загрузка сессии
  services/     # бизнес-логика (итерация 2+)
  integrations/ # OMS, TMS, Payments, CRM, LLM (итерация 2+)
  api/          # FastAPI app
  worker/       # ARQ worker
```

## Итерация 1 (диалоговое ядро)

- Согласие на ПДн / оферту перед сценариями
- FSM + сессии в Redis (TTL 30 мин), согласие хранится отдельно
- Главное меню (inline-кнопки)
- Intent matching: команды + keywords + callbacks
- AttemptLimiter (5 / 15 мин → блок 30 мин) — готов к верификации заказа
- Продление диалога после истечения сессии

## Бизнес-правила заказа

- **Смена адреса** — только до статуса `assembling` (`created` / `confirmed` / `paid`)
- **Смена времени / отмена** — до передачи курьеру (`handed_to_courier`)
- Реализация: `delivery_bot.services.order_policy`

## Итерация 2 (статус заказа)

- PostgreSQL-модели заказов + сид демо-данных
- Mock OMS REST (`/oms/v1/...`) в сервисе `api`
- Верификация: номер заказа + last4 телефона (лимит попыток)
- Без верификации — только факт «в пути»
- Кэш статуса в Redis (TTL 90 с)
- Персональная кнопка статуса после успешной проверки

Демо-заказы: `ORD-1001`…`ORD-1005`, телефон `+79001234567` (last4=`4567`).

## Итерация 3 (Telegram WebApp)

- UI виджета статуса: `http://localhost:8000/ui/?order_id=ORD-1001`
- API: `GET /webapp/v1/orders/{id}` (заголовок `X-Telegram-Init-Data`)
- После верификации в боте — кнопка «Открыть виджет статуса»
- Локальный просмотр без Telegram: `WEBAPP_DEV_BYPASS=true` + `?dev_user=1`
- Для открытия Mini App с телефона нужен **HTTPS**-URL (`TELEGRAM_WEBAPP_URL`, ngrok/tunnel)

## Итерация 4 (курьер + карта)

- Mock TMS: координаты курьера, движение к точке доставки
- Сценарий «Курьер» в боте (ФИО, телефон, ETA, кнопка карты)
- Вкладка «Карта» в Mini App (OpenStreetMap; `YANDEX_MAPS_API_KEY` — задел)
- Без GPS: сообщение + адрес доставки на карте
- API: `GET /oms/v1/orders/{id}/tracking`

## Итерация 5 (изменение адреса/времени)

- Адрес: только до `assembling`; вне зоны — отказ; окраина — доплата через mock payment
- Время: слоты из API, до передачи курьеру
- Меню «Изменить заказ» → адрес / время
- Демо: `ORD-1005` (confirmed) / `ORD-1002` (paid) — можно менять; `ORD-1001` (delivering) — адрес нельзя

## Итерация 6 (отмена + возврат)

- Полная отмена до передачи курьеру: причина из справочника + опциональный комментарий («Другое» — обязательно)
- Частичная отмена позиций с пропорциональным возвратом (mock payments, идемпотентность)
- API: `GET /oms/v1/cancel-reasons`, `POST /oms/v1/orders/cancel`, `POST /oms/v1/orders/partial-cancel`
- Демо: `ORD-1006` (paid, 3 позиции) — полная/частичная отмена; `ORD-1002`/`ORD-1005` — полная; `ORD-1001` — отказ

## Итерация 7 (FAQ + LLM)

- Knowledge base в PostgreSQL (10 демо-статей) + идемпотентный сид
- Keyword-поиск и `POST /faq/v1/ask` (API key); при low confidence — эскалация к оператору
- Опциональный LLM (`LLM_FAQ_ENABLED=true`): OpenAI-compatible; без ключа — MockLlm по KB
- Admin CRUD: `/admin/v1/faq/articles` (HTTP Basic: `ADMIN_BASIC_USER` / `ADMIN_BASIC_PASSWORD`)
- В боте: «FAQ» / `/faq` → темы или свободный вопрос

## Итерация 8 (претензии, отзывы, повтор)

- **Претензия**: verified order + delivered + окно 14 дней; причины + текст → mock CRM
- **Отзыв**: один раз после delivered (1–5 ⭐ + комментарий); пропуск → напоминание через ARQ worker
- **Повтор заказа**: из истории по last4; недоступные позиции пропускаются
- API: `/oms/v1/claims`, `/oms/v1/reviews`, `/oms/v1/orders/reorder`, `/webapp/v1/history`
- Демо: `ORD-1004` (delivered, last4 `4567`) — претензия / отзыв / повтор

## Итерация 9 (эскалация / CRM handoff)

- Полный handoff: тикет в mock CRM с контекстом (заказ, FAQ, intent)
- Operator takeover: сообщения клиента → CRM; ответы оператора → Telegram (ARQ worker)
- API: `POST /crm/v1/tickets`, admin `/admin/v1/tickets/{id}/reply`
- В боте: «Оператор» / кнопка из FAQ → описание → режим handoff
- Демо ответа оператора: Basic auth admin + `POST .../tickets/{id}/reply`

## Итерация 10 (harden)

- **PII masking** в structlog: телефоны, last4, токены, URL с паролями
- **Prometheus**: `GET /metrics` (API `:8000`, bot health `:8081`) — HTTP, intents, verify, escalations
- **X-Request-ID** на каждый запрос API
- Скрипт ответа оператора с UTF-8: `python scripts/admin_reply.py 2 "Текст"`
- Флаг `METRICS_ENABLED=false` отключает `/metrics`

## Итерации

См. согласованное ТЗ: Итерация 0 (каркас) → Итерация 1 (диалог) → … → Итерация 10 (harden).
