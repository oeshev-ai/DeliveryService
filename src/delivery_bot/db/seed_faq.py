"""Сид FAQ knowledge base."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.db.models import FaqArticleModel
from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)

_SEED: list[dict[str, str]] = [
    {
        "slug": "delivery-zone",
        "title": "Зона доставки",
        "category": "delivery",
        "question": "Куда вы доставляете?",
        "answer": (
            "Доставляем по Москве в пределах МКАД без доплаты.\n"
            "Ближайшее Подмосковье (Химки, Мытищи, Люберцы, Одинцово, "
            "Зеленоград, Новая Москва) — с доплатой ~250 ₽.\n"
            "Другие города (Казань, СПб и т.п.) — вне зоны."
        ),
        "keywords": "зона,доставка,мкад,москва,куда,город,химки,зеленоград",
    },
    {
        "slug": "min-order",
        "title": "Минимальная сумма заказа",
        "category": "payment",
        "question": "Какая минимальная сумма заказа?",
        "answer": ("Минимальная сумма заказа — 500 ₽.\nПри меньшей сумме оформление недоступно."),
        "keywords": "минимальная,сумма,заказ,минимум,500",
    },
    {
        "slug": "payment-methods",
        "title": "Способы оплаты",
        "category": "payment",
        "question": "Как можно оплатить заказ?",
        "answer": (
            "Оплата картой онлайн при оформлении.\n"
            "Доплата за смену адреса на окраину — через бота (mock-платёж в демо).\n"
            "Наличными курьеру в MVP не принимаем."
        ),
        "keywords": "оплата,оплатить,карта,платеж,деньги,способ",
    },
    {
        "slug": "schedule",
        "title": "График и слоты доставки",
        "category": "delivery",
        "question": "Какой график доставки?",
        "answer": (
            "Доставка ежедневно. Типовые слоты:\n"
            "• сегодня 16:00–18:00\n"
            "• сегодня 18:00–20:00\n"
            "• сегодня 20:00–22:00\n"
            "• завтра 12:00–14:00\n"
            "Слот можно сменить в боте, пока заказ не передан курьеру."
        ),
        "keywords": "график,время,слот,расписание,часы,когда",
    },
    {
        "slug": "change-address",
        "title": "Изменение адреса",
        "category": "order",
        "question": "Можно ли изменить адрес доставки?",
        "answer": (
            "Да, через меню «Изменить заказ» → «Изменить адрес».\n"
            "Адрес можно менять только до передачи в сборку "
            "(статусы created / confirmed / paid).\n"
            "Вне зоны — отказ; окраина — доплата."
        ),
        "keywords": "изменить,адрес,сменить,другой адрес",
    },
    {
        "slug": "cancel-order",
        "title": "Отмена заказа",
        "category": "order",
        "question": "Как отменить заказ?",
        "answer": (
            "Откройте «Отмена» в меню бота.\n"
            "Можно отменить весь заказ или отдельные позиции "
            "до передачи курьеру. Возврат оформляется автоматически (mock).\n"
            "После передачи курьеру — только через оператора."
        ),
        "keywords": "отмен,отменить,возврат,cancel",
    },
    {
        "slug": "courier-where",
        "title": "Где курьер",
        "category": "delivery",
        "question": "Как узнать, где курьер?",
        "answer": (
            "Нажмите «Курьер» в меню или откройте виджет статуса → вкладка «Карта».\n"
            "Покажем ФИО, телефон и ETA. Трекинг доступен, когда заказ у курьера."
        ),
        "keywords": "курьер,где курьер,трек,карта,водитель",
    },
    {
        "slug": "order-status",
        "title": "Статус заказа",
        "category": "order",
        "question": "Как узнать статус заказа?",
        "answer": (
            "«Статус заказа» в меню: введите номер (ORD-…) и last4 телефона.\n"
            "Без проверки покажем только факт «в пути», если заказ доставляется.\n"
            "После проверки доступен персональный статус и Mini App."
        ),
        "keywords": "статус,где заказ,отследить,трекинг",
    },
    {
        "slug": "refund",
        "title": "Возврат средств",
        "category": "payment",
        "question": "Когда вернут деньги при отмене?",
        "answer": (
            "При полной или частичной отмене через бота возврат оформляется сразу "
            "(в демо — mock-платёж с идемпотентным ключом).\n"
            "Срок зачисления на карту в проде зависит от банка (обычно 1–5 дней)."
        ),
        "keywords": "возврат,деньги,refund,средства",
    },
    {
        "slug": "operator",
        "title": "Связь с оператором",
        "category": "support",
        "question": "Как связаться с оператором?",
        "answer": (
            "Кнопка «Оператор» в меню или «Связаться с оператором», "
            "когда бот не может помочь.\n"
            "Полноценный handoff в CRM: создайте тикет через «Оператор» в боте "
            "или эскалацию из FAQ. Ответ оператора придёт в чат; admin API: "
            "/admin/v1/tickets."
        ),
        "keywords": "оператор,поддержка,человек,менеджер,помощь",
    },
]


async def seed_faq(session: AsyncSession) -> None:
    """Добавляет отсутствующие статьи FAQ (не перезаписывает существующие)."""
    added = 0
    for row in _SEED:
        exists = await session.scalar(
            select(FaqArticleModel.id).where(FaqArticleModel.slug == row["slug"])
        )
        if exists is not None:
            continue
        session.add(FaqArticleModel(**row, is_active=True))
        added += 1
    if added:
        await session.flush()
        logger.info("seed_faq_done", added=added, total=len(_SEED))
    else:
        logger.info("seed_faq_skipped", reason="all_present", total=len(_SEED))
