# Delivery Service Chatbot

Пакет `delivery-bot` `0.1.0`. Клиентский бот поддержки доставки: процесс Telegram (`python -m delivery_bot`), HTTP API (`uvicorn delivery_bot.api.app:app`) и ARQ-воркер (`python -m delivery_bot.worker`).

Зависимости приложения: Python `>=3.11` (образ и CI — 3.12), aiogram 3.31.0, FastAPI 0.115.14, SQLAlchemy 2.0.43 (asyncio) + asyncpg, Alembic 1.16.5, Redis-клиент 5.3.1, ARQ 0.26.3, Pydantic 2.11.9 / pydantic-settings 2.10.1, structlog 25.4.0.

## Запуск

```bash
cp .env.example .env
# COMPOSE_PROJECT_NAME=delivery — имя проекта в комментарии compose
docker compose up -d --build
```

`docker-compose.yml` задаёт `name: delivery`. Сервисы `postgres` (`postgres:16-alpine`) и `redis` (`redis:7-alpine`) без секции `ports`. API публикует `${HOST_API_PORT:-18000}:8000`, health бота — `${HOST_BOT_HEALTH_PORT:-18081}:8081`.

| Сервис | Команда | Зависимости |
| --- | --- | --- |
| `api` | `alembic upgrade head`, затем uvicorn на `0.0.0.0:8000` | postgres и redis `service_healthy`; healthcheck `GET /ready` |
| `bot` | `python -m delivery_bot` | postgres, redis и api `service_healthy`; `OMS_BASE_URL=http://api:8000`; healthcheck `GET http://localhost:8081/health` |
| `worker` | `python -m delivery_bot.worker` | redis `service_healthy` |

Образ (`Dockerfile`): `python:3.12-slim`, `PYTHONPATH=/app/src`, пользователь `app` (uid/gid 10001), `pip install .`, каталог `webapp` копируется в образ. CMD по умолчанию — uvicorn на порту 8000; compose его переопределяет. `.dockerignore` содержит отдельные токены `.env`, `.venv` и `tests` (`tests/test_alembic_tooling.py`, `test_dockerignore_excludes_secrets_venv_and_tests`).

Локальные проверки (как в `.github/workflows/ci.yml`, Python 3.12):

```bash
pip install -e ".[dev]"
ruff check src tests
ruff format --check src tests
mypy
pytest
```

`tests/test_history_queries.py`, `tests/test_review_concurrency.py` и `tests/test_escalation.py` открывают движок по `Settings.database_url`. В CI для этого поднят `postgres:16` и задан `DATABASE_URL=postgresql+asyncpg://delivery:delivery_secret@localhost:5432/delivery`, `APP_ENV=test`. Тесты Redis в `tests/test_session_limits.py`, `tests/test_session_lock.py` и `tests/test_payment_idempotency.py` используют `fakeredis` (dev-зависимость `fakeredis[lua]`).

## Процессы

Бот (`src/delivery_bot/bot_app.py`) поднимает health-сервер aiohttp (`start_health_server`) и вешает `DialogSessionMiddleware` на `dp.update`. Лимитер попыток создаётся из `Settings.verify_max_attempts`, `verify_attempt_window_seconds`, `verify_block_seconds`. Клиенты OMS, post-delivery, FAQ и CRM ходят на `Settings.oms_base_url` с `Settings.api_key`. Трекинг в процессе бота — `MockTmsService`.

API (`create_api_app` в `src/delivery_bot/api/__init__.py`) в lifespan вызывает `seed_orders` и `seed_faq`, кладёт в `app.state` движок, фабрику сессий и Redis. Статика Mini App монтируется на `/ui`, если каталог `webapp/static` существует. Документация FastAPI: `/docs`, `/redoc`.

`GET /health` API без lifespan отвечает 200 и `service=api` (`tests/test_health.py`, `test_api_health_ok`). У бота `GET /health` отвечает 200 и `service=bot`; `GET /ready` без Redis — 503 и `checks.redis=false`, с Redis, отвечающим на ping, — 200 и `checks.redis=true` (`test_bot_health_ok`, `test_bot_ready_without_redis_not_ready`, `test_bot_ready_with_redis_ok`).

Воркер (`WorkerSettings` в `src/delivery_bot/worker/__init__.py`): функции `heartbeat`, `process_review_reminders`, `process_operator_replies`. Cron: heartbeat в минуты 0 и 30, напоминания об отзыве каждые 5 минут, доставка ответов оператора каждые 2 минуты. Очередь напоминаний — Redis sorted set `review:reminder:queue`.

`ViberAdapter`, `WhatsAppAdapter` и `WebWidgetAdapter`: `is_ready()` возвращает `False` (`tests/test_health.py`, `test_stub_channels_not_ready`).

## Конфигурация

`Settings` (`src/delivery_bot/config.py`) читает окружение и файл `.env`. Имена ниже — переменные окружения этих полей. Значения — умолчания в коде.

| Переменная | Умолчание |
| --- | --- |
| `APP_ENV` | `local` |
| `APP_NAME` | `delivery-bot` |
| `LOG_LEVEL` | `INFO` |
| `LOG_JSON` | `true` |
| `TELEGRAM_BOT_TOKEN` | пустая строка |
| `TELEGRAM_WEBAPP_URL` | `http://localhost:8000/ui` |
| `DATABASE_URL` | `postgresql+asyncpg://delivery:delivery_secret@localhost:5432/delivery` |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` |
| `API_KEY` | `dev_api_key_change_me` |
| `ADMIN_BASIC_USER` / `ADMIN_BASIC_PASSWORD` | `admin` / `admin_change_me` |
| `HEALTH_HOST` / `HEALTH_PORT` | `0.0.0.0` / `8081` |
| `SESSION_TTL_SECONDS` | `1800` |
| `CONSENT_TTL_SECONDS` | `31536000` |
| `VERIFY_MAX_ATTEMPTS` | `5` |
| `VERIFY_ATTEMPT_WINDOW_SECONDS` | `900` |
| `VERIFY_BLOCK_SECONDS` | `1800` |
| `OMS_BASE_URL` | `http://localhost:8000` |
| `OMS_TIMEOUT_SECONDS` | `3.0` |
| `STATUS_CACHE_TTL_SECONDS` | `90` |
| `WEBAPP_DEV_BYPASS` | `true` |
| `WEBAPP_BINDING_TTL_SECONDS` | `86400` |
| `WEBAPP_INIT_DATA_MAX_AGE_SECONDS` | `86400` |
| `LLM_FAQ_ENABLED` | `false` |
| `PAYMENT_MOCK` | `true` |
| `OMS_MOCK` | `true` |
| `YANDEX_MAPS_API_KEY` | пустая строка |
| `LLM_API_KEY` | пустая строка |
| `LLM_BASE_URL` | `https://api.openai.com/v1` |
| `LLM_MODEL` | `gpt-4o-mini` |
| `LLM_MOCK_LATENCY_MS` | `80` |
| `CLAIM_WINDOW_DAYS` | `14` |
| `REVIEW_REMINDER_DELAY_SECONDS` | `3600` |
| `METRICS_ENABLED` | `true` |

`HOST_API_PORT`, `HOST_BOT_HEALTH_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` читает compose, не `Settings`. В compose `DATABASE_URL` и `REDIS_URL` указывают на хосты `postgres` и `redis`; у бота `TELEGRAM_WEBAPP_URL` по умолчанию `http://localhost:18000/ui`.

`payment_mock` и `oms_mock` в `src/` встречаются только как поля `Settings`. `cancel_routes` и `change_routes` создают `MockPaymentGateway`. `bot_app` создаёт `MockTmsService`.

При `APP_ENV=production` валидатор `Settings._reject_insecure_production` описан в разделе ниже.

`GET /metrics` API отдаёт тело `render_metrics()`. Пустое тело — ответ 404 с текстом `metrics disabled`.

## Данные

Одна ревизия Alembic: `48a5fd403aa1` (`migrations/versions/48a5fd403aa1_initial_schema.py`). `migrations/env.py` берёт URL через `set_sqlalchemy_url(get_settings().database_url)` и гоняет миграции асинхронным движком.

Таблицы ревизии `48a5fd403aa1` и моделей в `src/delivery_bot/db/models.py`: `orders`, `order_items`, `faq_articles`, `claims`, `reviews`, `escalation_tickets`, `escalation_messages`. У `reviews` ограничение `uq_reviews_order_user` на `(order_id, user_id)`. Ревизия перед созданием ограничения удаляет дубликаты с меньшим `id`.

Ревизия `e6b1c0a4d2f3` добавляет на `orders` хранимую колонку `phone_last4` (`right(regexp_replace(phone, '[^0-9]', '', 'g'), 4)`) и индекс `ix_orders_phone_last4`.

`seed_orders` добавляет отсутствующие строки и не перезаписывает уже существующий `id`. Телефон `+79001234567` (последние 4 цифры `4567`): `ORD-1001` `delivering`, `ORD-1002` `paid`, `ORD-1004` `delivered`, `ORD-1005` `confirmed`, `ORD-1006` `paid`. Телефон `+79007654321`: `ORD-1003` `assembling`. Для уже лежащего `ORD-1004` в статусе `delivered` без `delivered_at` проставляется момент «сутки назад».

Статусы `OrderStatus`: `created`, `confirmed`, `paid`, `assembling`, `ready`, `handed_to_courier`, `delivering`, `delivered`, `cancelled`.

## HTTP

Префикс `/oms/v1`, модуль `oms_routes.py`. Все четыре обработчика зависят от `require_api_key`. Сессия БД (`get_db_session`) делает `commit` после успешного выхода и `rollback` при исключении.

| Метод и путь | Поведение в коде |
| --- | --- |
| `GET /oms/v1/orders/{order_id}/public` | `OmsRepository.get_public`; нет заказа — 404 |
| `GET /oms/v1/orders/{order_id}` | полный `OrderDTO` через `to_order_dto`; нет заказа — 404 |
| `POST /oms/v1/orders/verify` | `OmsRepository.verify` после `strip().upper()` у номера; несовпадение — `VerifyResponse(ok=False, reason="not_found_or_mismatch")` |
| `GET /oms/v1/orders?phone_last4=` | query ровно 4 цифры; `OmsRepository.list_by_last4` |

`require_api_key` сравнивает заголовок `X-API-Key` с `Settings.api_key` через `secrets.compare_digest`. Проверка статуса на `GET /oms/v1/cancel-reasons` — в разделе ниже.

`/admin/v1/faq` и `/admin/v1/tickets`: `_require_admin` сравнивает HTTP Basic (`admin_basic_user`, `admin_basic_password`) через `secrets.compare_digest`. Несовпадение — 401, `detail="Unauthorized"`, заголовок `WWW-Authenticate: Basic`.

Префикс `/webapp/v1`:

| Метод и путь | Поведение в коде |
| --- | --- |
| `GET /webapp/v1/orders/{order_id}` | `get_webapp_user`, затем `WebAppBindingStore.can_access`. Нет доступа — 403, текст `Order is not linked to this user. Verify it in the bot first.` Нет заказа — 404. Тело `WebAppOrderView`, координаты из `MockTmsService.tracking_for` |
| `GET /webapp/v1/history` | binding пользователя; без binding — пустой список. Иначе `OmsRepository.list_full_by_last4(binding.phone_last4, limit=12)` и отзывы этого `user_id` |

`get_webapp_user`: при `webapp_dev_bypass` и `app_env` из `{local, test}` и заголовке `X-WebApp-Dev-User` возвращает пользователя с этим id. Иначе обязателен `X-Telegram-Init-Data`; `validate_init_data` при `TelegramInitDataError` даёт 401. Redis в `app.state` отсутствует — 503 `Redis is not configured`.

`create_api_app` также подключает роутеры с префиксами `/oms/v1` (change, cancel, post-delivery, tms), `/faq/v1`, `/crm/v1`, `/admin/v1/faq`, `/admin/v1/tickets`.

## Архитектурные решения

Параллельные вызовы `AttemptLimiter.hit` (`src/delivery_bot/dialog/limits.py`, скрипт `_HIT_LUA`) разрешают ровно `max_attempts - 1` попыток, затем ставят блок и удаляют ключ счётчика. После блока `AttemptLimiter.check` возвращает `allowed=False`. `AttemptLimiter.reset` снова разрешает попытки и обнуляет счётчик.

`DialogSessionMiddleware` (`src/delivery_bot/middleware/__init__.py`) сериализует апдейты одного пользователя: второй обработчик видит состояние, сохранённое первым. `_release_lock` (Lua `_RELEASE_LOCK_LUA`) удаляет ключ лока только при совпадении токена. Если лок не получен, handler не вызывается. `_extract_user_id` читает id из `Update.message.from_user` и из `data["event_from_user"]`.

`RedisSessionStore.get` без записи создаёт сессию в состоянии `AWAITING_CONSENT`. `save` пишет сессию и, при принятом согласии, отдельный ключ согласия. `clear_session` удаляет сессию; следующая `get` сохраняет `consent_accepted=True` и ставит состояние `SESSION_EXPIRED`.

`MockPaymentGateway.refund` (`src/delivery_bot/integrations/payments/mock.py`, `_idempotent_op`) с одним ключом и одной суммой при двух параллельных вызовах возвращает один `payment_id` и `ok=True`. Тот же ключ с другой суммой возвращает `ok=False`, в `message` есть «другой суммой». Разные ключи дают разные `payment_id`.

`Settings._reject_insecure_production`: при `app_env=local` принимаются `api_key=dev_api_key_change_me`, `admin_basic_password=admin_change_me`, пустой `telegram_bot_token` и `webapp_dev_bypass=True`. При `app_env=production` этот набор поднимает `ValidationError` с текстом `Insecure production configuration`. Набор с другими секретами, непустым токеном и `webapp_dev_bypass=False` создаётся.

`require_api_key` (`src/delivery_bot/api/auth.py`): `GET /oms/v1/cancel-reasons` с неверным `X-API-Key` отвечает 401 и `detail == "Invalid API key"`. Верный ключ из `get_settings().api_key` отвечает 200 и JSON-списком.

`validate_init_data` (`src/delivery_bot/webapp/telegram_auth.py`) с верной HMAC-подписью возвращает `id` пользователя. Строка с испорченным hash поднимает `TelegramInitDataError`. `WebAppBindingStore.grant` (`src/delivery_bot/webapp/bindings.py`) открывает `can_access` этому пользователю на выданный `order_id`; другой `order_id` и другой пользователь получают `False`. `is_telegram_webapp_url` возвращает `True` для `https` с непустым netloc; для `http://localhost:8000/ui` и для `None` возвращает `False`. `_webapp_order_url` кладёт `order_id` в query; с аргументом `tab` добавляет `tab` в query и fragment `#tab=`.

`phone_last4` (`src/delivery_bot/integrations/oms/repository.py`) для `+79001234567` и `900-123-45-67` возвращает `4567`. `OmsRepository.list_full_by_last4` фильтрует равенством по колонке `orders.phone_last4` и применяет `LIMIT` уже к совпадениям: заказ с телефоном `+7 (900) 123-45-67` находится по `4567` при `limit=12`, когда в таблице есть 104 более новые строки с другим телефоном. В этом запросе нет `regexp_replace`. Сборка списка истории вызовами `list_full_by_last4(..., limit=12)` и `PostDeliveryRepository.get_reviews_for_orders` для пяти заказов выполняет не больше трёх SQL-запросов.

`normalize_order_id` превращает `1001` и `ord-1001` в `ORD-1001`; для `abc` возвращает `None`. `OrderStatusService.select_order` при уже лежащем в контексте `phone_last4` вызывает `verify` с этим last4 и оставляет состояние вне `AWAITING_PHONE_LAST4`. Без предыдущей верификации `select_order` переводит сессию в `AWAITING_PHONE_LAST4`. При ответе OMS `ok=False` текст `handle_input` содержит «попыток». В сценарии с публичным статусом «в пути» ввод `1001` ведёт в `AWAITING_PHONE_LAST4`, ввод `4567` записывает `verified_order_id=ORD-1001` и включает в текст имя курьера и адрес.

`ReviewModel` задаёт `UniqueConstraint("order_id", "user_id", name="uq_reviews_order_user")`. Два параллельных `PostDeliveryRepository.submit_review` на одну пару `order_id`+`user_id` оставляют одну строку `reviews`; оба вызова возвращают эту пару. Тест создаёт таблицы через `Base.metadata.create_all`.

`set_sqlalchemy_url` (`src/delivery_bot/db/alembic_url.py`) записывает URL так, что пароль `p%40ss` читается обратно тем же значением. `migrations/env.py` и `scripts/stamp_legacy_db.py` вызывают `set_sqlalchemy_url` и не вызывают `set_main_option("sqlalchemy.url"`. `stamp_legacy_db.main` завершает проверку БД своим `asyncio.run` и только потом вызывает `alembic stamp`; когда подменённый `stamp` сам вызывает `asyncio.run`, `main` возвращает 0.

`MockTmsService.tracking_for` при `status="delivering"` и имени курьера ставит `gps_available=True` и непустые `courier_lat`/`courier_lon`. При `status="paid"` без имени курьера `gps_available=False` и `courier_lat is None`.
