Контекст проекта
Telegram-бот клиентской поддержки сервиса доставки. Стек: Python 3.12, aiogram 3, FastAPI, SQLAlchemy 2.0 (async) + PostgreSQL, Redis, ARQ worker, Docker Compose. Интеграции OMS/TMS/Payments/CRM — моки (так и задумано, не заменять на реальные). Бизнес-правила статусов заказа — в src/delivery_bot/services/order_policy.py. Тесты — pytest + fakeredis + AsyncMock, asyncio_mode=auto.
Цель доработки: закрыть пробелы в CI, конкурентности, миграциях и безопасности, довести репозиторий до уровня «флагманский проект портфолио». Новые фичи не добавляем.
Глобальные правила (обязательны для всех задач)
Одна задача = один коммит, conventional commits (fix:, feat:, ci:, refactor:, docs:, test:).
После каждой задачи зелёные: ruff check, mypy, pytest. Если тесты упали — чини в рамках этой же задачи, не переходи к следующей.
Не менять публичные контракты: URL эндпоинтов, response-модели, callback_data, тексты бизнес-правил. Исключения явно указаны в задачах.
Весь новый код: полные type hints, docstrings на русском в стиле существующих, логирование через structlog без PII (использовать существующий security/pii.py, не логировать сырые телефоны/токены).
Runtime-зависимость добавлять только при явной необходимости; инструменты разработки — только в dev-зависимости.
При изменении конфигов синхронизировать Settings ↔ .env.example ↔ README.
Если задача конфликтует с существующим поведением и ТЗ не покрывает случай — остановиться и спросить, не додумывать.
Итерация 1 — CI и инструменты качества (P0, ~0.5 дня)
1.1. Консолидация зависимостей
Перенести runtime-зависимости из requirements.txt в [project].dependencies в pyproject.toml (сейчас там пустой список — рассинхрон).
Добавить [project.optional-dependencies] dev: pytest, pytest-asyncio, pytest-cov, fakeredis[lua] (extra lua обязателен — понадобится в итерации 3), ruff, mypy.
requirements.txt удалить или оставить как shim -e .[dev]; обновить Dockerfile (pip install . вместо -r requirements.txt) и README.
1.2. Линтеры и типизация
В pyproject.toml: ruff (line-length 100, select: E, F, I, UP, B, SIM, ASYNC) и mypy (плагин pydantic.mypy; strict для services/, dialog/, security/, webapp/telegram_auth.py; остальное — базовый режим, без ignore_errors).
Исправить все замечания линтеров. Автофиксы — отдельным коммитом от ручных правок.
1.3. GitHub Actions
.github/workflows/ci.yml: на push/PR в main, три job'а: lint (ruff check + format check), typecheck (mypy), test (pytest + coverage).
Важно: tests/test_escalation.py::test_crm_repository_create_and_operator_reply ходит в реальную БД. В job test поднять service container postgres:16-alpine и прокинуть DATABASE_URL, APP_ENV=test.
Кэш pip, Python 3.12.
1.4. README — базовая гигиена
Убрать артефакт """ в начале заголовка.
Бейджи: CI status, Python version.
Раздел «Тесты»: как запустить локально (включая требование к Postgres для интеграционного теста).
DoD итерации: CI зелёный на GitHub, бейдж виден, pip install -e .[dev] поднимает окружение с нуля.
Итерация 2 — Security quick wins (P0, ~0.5 дня)
2.1. Constant-time сравнение API key
src/delivery_bot/api/oms_routes.py, _require_api_key: заменить != на secrets.compare_digest (по образцу _require_admin в admin_faq_routes.py). Проверить все остальные места сравнения секретов grep'ом.
Тест: неверный ключ → 401, верный → проходит.
2.2. XSS в Mini App
webapp/static/assets/app.js: loadHistory() собирает HTML через innerHTML с интерполяцией ${o.status_label}, ${o.delivery_slot} и т.д.; catch-блок тоже вставляет err.message в innerHTML.
Переписать рендер истории на DOM API (createElement + textContent) либо добавить escapeHtml() и экранировать все интерполяции, включая сообщения об ошибках. Статусная панель уже использует textContent — не трогать.
Поведение UI (клики по карточкам, табы) сохранить.
2.3. Уникальность отзыва на уровне БД
ReviewModel: добавить UniqueConstraint("order_id", "user_id").
PostDeliveryRepository.submit_review / skip_review: обернуть вставку в обработку IntegrityError → перечитать существующую запись и вернуть её (гонка двух параллельных сабмитов не должна падать 500-й).
Тест: два параллельных submit_review через asyncio.gather → одна запись, оба вызова успешны. (Миграция для существующих БД — в итерации 4.)
2.4. Guard продакшен-конфигов
В Settings добавить model_validator: при app_env == "production" падать с понятной ошибкой, если api_key, admin_basic_password равны дефолтам, telegram_bot_token пустой или webapp_dev_bypass=true.
Тесты: production + дефолты → ошибка; local + дефолты → ок.
2.5. Обновление зависимостей
Поднять версии в рамках текущих мажоров до актуальных stable (особенно aiohttp — у запиненной 3.10.10 есть известные уязвимости, минимум patch-бамп). Точные версии запинить.
При обновлении pytest-asyncio сохранить asyncio_mode = "auto" и asyncio_default_fixture_loop_scope = "function".
Прогнать весь套件, проверить changelog'и на breaking changes. Если aiogram/fastapi ломают тесты — фиксить в этом же коммите или откатить конкретную зависимость с комментарием.
DoD: все тесты зелёные на новых версиях, XSS-векторы закрыты, constraint в модели.
Итерация 3 — Конкурентность (P1, ~1 день, ядро доработки)
3.1. Атомарный AttemptLimiter
src/delivery_bot/dialog/limits.py: метод hit() сейчас делает TTL → INCR → EXPIRE → SET block → DEL отдельными командами. Заменить на один Lua-скрипт (redis.register_script):
lua
-- KEYS[1]=attempts, KEYS[2]=block
-- ARGV[1]=max_attempts, ARGV[2]=window_sec, ARGV[3]=block_sec
local ttl = redis.call('TTL', KEYS[2])
if ttl > 0 then return {0, tonumber(ARGV[1]), ttl} end
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
if n >= tonumber(ARGV[1]) then
  redis.call('SET', KEYS[2], '1', 'EX', ARGV[3])
  redis.call('DEL', KEYS[1])
  return {0, n, tonumber(ARGV[3])}
end
return {1, n, 0}
check() оставить read-only как есть (advisory), авторитетное решение — в hit().
Тесты: N параллельных hit() через asyncio.gather → ровно max_attempts-1 разрешённых, остальные заблокированы; счётчик не остаётся без TTL. Убедиться, что fakeredis исполняет Lua (нужен fakeredis[lua] из задачи 1.1).
3.2. Идемпотентность платежей через SET NX
src/delivery_bot/integrations/payments/mock.py: заменить паттерн GET → SET на SET key payload NX EX 86400, где payload — JSON {payment_id, amount}.
Если ключ уже занят: прочитать payload; сумма совпадает → вернуть сохранённый результат; сумма отличается → ok=False, message «ключ идемпотентности уже использован с другой суммой». Обработать edge: ключ истёк между SET NX и GET → одна повторная попытка.
Тесты: два параллельных refund с одним ключом и суммой → один payment_id; тот же ключ с другой суммой → отказ; разные ключи → разные платежи.
3.3. Лок сессии на пользователя
src/delivery_bot/middleware/__init__.py: сейчас read-modify-write без лока — два быстрых апдейта затирают FSM.
Обернуть обработку в Redis-лок dialog:lock:{channel}:{user_id}: SET NX PX 10000 с токеном (uuid), ожидание до 5 с (ретраи ~100 мс), освобождение Lua-скриптом compare-and-del (не удалять чужой лок).
Если лок не получен за 5 с: не вызывать handler, ответить «Обрабатываю ваше предыдущее сообщение, секунду…», событие не сохранять.
Логировать contention (structlog, без PII).
Тесты: два параллельных апдейта одного пользователя сериализуются (второй видит состояние, сохранённое первым); лок протухшего holder'а не удаляется чужим освобождением.
DoD: три гонки закрыты, каждая покрыта конкурентным тестом с asyncio.gather. В README (итерация 5) появится раздел про эти решения.
Итерация 4 — Alembic (P1, ~0.5–1 день)
4.1. Внедрение
Добавить alembic (runtime-зависимость), alembic init -t async migrations.
env.py: URL из Settings.database_url, target_metadata = Base.metadata с импортом всех моделей.
Сгенерировать initial-миграцию по текущим моделям (включая UniqueConstraint из 2.3).
4.2. Миграция constraint с дедупликацией
В initial-миграции (или отдельной, если initial генерируется без constraint): перед созданием уникального индекса на reviews удалить дубли, оставив запись с максимальным id:
sql
DELETE FROM reviews a USING reviews b
WHERE a.order_id = b.order_id AND a.user_id = b.user_id AND a.id < b.id;
4.3. Интеграция в запуск
Удалить db/migrate.py (apply_schema_patches) и его вызов в lifespan.
init_db/create_all оставить только для тестов; прод-путь — миграции.
Команда api в docker-compose: sh -c "alembic upgrade head && uvicorn delivery_bot.api.app:app --host 0.0.0.0 --port 8000".
Для существующих БД, созданных через create_all: описать в README процедуру alembic stamp head (или скрипт scripts/stamp_legacy_db.py, который stamp'ит только если таблицы уже есть и alembic_version пуста).
README: раздел «Миграции» (создать, применить, откатить).
DoD: чистый Postgres поднимается через docker compose up без ручных действий; существующая БД после stamp корректно накатывает последующие миграции. Проверить оба сценария вручную и описать в коммите.
Итерация 5 — Производительность и витрина (P1, ~0.5 дня)
5.1. N+1 в истории заказов
api/webapp_routes.py::get_order_history: цикл get_by_id + get_review на каждый заказ (до 24+ запросов).
Добавить в OmsRepository метод получения полных заказов по last4 одним запросом с selectinload(items); отзывы — одним запросом WHERE order_id IN (...) AND user_id = :uid → dict.
Итого ≤ 3 запроса на эндпоинт. Тест: счётчик запросов через SQLAlchemy event listener.
5.2. README как витрина
Убрать артефакты, добавить:
mermaid-диаграмму архитектуры (bot → api → postgres/redis; worker; Mini App);
секцию «Скриншоты» с путями docs/screenshots/ (бот, Mini App статус, карта, история) — сами картинки владелец добавит вручную, оставить placeholder'ы;
раздел «Архитектурные решения и компромиссы»: моки интеграций и почему; атомарный лимитер (Lua); идемпотентность через SET NX и поведение при конфликте сумм; лок сессий и UX при contention; Alembic и путь со старых БД; graceful degradation на кэше при недоступном OMS. Это ключевой раздел для собеседований — написать содержательно, не отпиской.
Обновить разделы запуска/тестов под все изменения итераций 1–4.
DoD: README читается за 3 минуты и даёт полную картину; история заказов без N+1.
Итерация 6 — Hardening (P2, опционально, ~0.5 дня)
Dockerfile: non-root user; не копировать tests/ в образ; multi-stage по желанию.
docker-compose: добавить healthcheck сервису bot (curl localhost:8081/health) — у api он есть, у bot нет.
Тесты: убрать обращения к приватным API (_normalize_order_id, service._cache в tests/test_order_status.py, tests/test_cancel.py) — тестировать через публичное поведение или сделать хелперы публичными.
.env.example: комментарии, какие значения обязательны к смене в production (в связке с guard из 2.4).
