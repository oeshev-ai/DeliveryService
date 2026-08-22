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
  dialog/       # Dialog Manager / FSM (итерация 1+)
  services/     # бизнес-логика (итерация 2+)
  integrations/ # OMS, TMS, Payments, CRM, LLM (итерация 2+)
  api/          # FastAPI app
  worker/       # ARQ worker
```

## Итерации

См. согласованное ТЗ: Итерация 0 (каркас) → … → Итерация 10 (harden).
"""
