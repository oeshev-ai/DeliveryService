"""
Delivery Service Chatbot
========================

Клиентский Telegram-бот для сервиса доставки (еда/товары).
MVP: aiogram + PostgreSQL + Redis + FastAPI (админка/WebApp backend) + моки OMS/TMS/Payments.

## Быстрый старт (Docker)

```bash
cp .env.example .env
# Укажите TELEGRAM_BOT_TOKEN в .env

docker compose up --build
```

Сервисы:
- `bot` — Telegram-бот + `/health` на порту 8081
- `api` — FastAPI (health/ready; админка и WebApp API появятся в следующих итерациях)
- `postgres`, `redis`
- `worker` — заготовка под фоновые задачи (ARQ)

Локальная проверка здоровья:

```bash
curl http://localhost:8081/health
curl http://localhost:8000/health
```

## Локальная разработка без Docker (опционально)

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
# Поднимите postgres/redis или укажите локальные URL
python -m delivery_bot
```

## Тесты

```bash
pytest
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

## Итерации

См. согласованное ТЗ: Итерация 0 (каркас) → Итерация 1 (диалог) → … → Итерация 10 (harden).
"""
