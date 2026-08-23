"""Идемпотентный сид демо-заказов для mock OMS."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.db.models import OrderItemModel, OrderModel
from delivery_bot.logging_setup import get_logger
from delivery_bot.services.order_policy import OrderStatus

logger = get_logger(__name__)

# Демо-телефон: +7 900 123-45-67 → last4 = 4567
DEMO_PHONE = "+79001234567"
DEMO_PHONE_ALT = "+79007654321"  # last4 = 4321


def _demo_orders() -> list[OrderModel]:
    return [
        OrderModel(
            id="ORD-1001",
            phone=DEMO_PHONE,
            status=OrderStatus.DELIVERING.value,
            address="Москва, ул. Тверская, 10, кв. 5",
            delivery_slot="сегодня 18:00–20:00",
            eta_minutes=25,
            courier_name="Иван Петров",
            courier_phone="+79001112233",
            total_amount=Decimal("1290.00"),
            items=[
                OrderItemModel(
                    name="Пицца Маргарита",
                    quantity=1,
                    price=Decimal("690.00"),
                    available=True,
                ),
                OrderItemModel(
                    name="Кола 0.5л",
                    quantity=2,
                    price=Decimal("150.00"),
                    available=True,
                ),
                OrderItemModel(
                    name="Соус фирменный",
                    quantity=1,
                    price=Decimal("50.00"),
                    available=True,
                ),
            ],
        ),
        OrderModel(
            id="ORD-1002",
            phone=DEMO_PHONE,
            status=OrderStatus.PAID.value,
            address="Москва, ул. Арбат, 15",
            delivery_slot="сегодня 20:00–22:00",
            eta_minutes=90,
            courier_name=None,
            courier_phone=None,
            total_amount=Decimal("890.00"),
            items=[
                OrderItemModel(
                    name="Суши сет №3",
                    quantity=1,
                    price=Decimal("890.00"),
                    available=True,
                ),
            ],
        ),
        OrderModel(
            id="ORD-1003",
            phone=DEMO_PHONE_ALT,
            status=OrderStatus.ASSEMBLING.value,
            address="Москва, пр. Мира, 40",
            delivery_slot="завтра 12:00–14:00",
            eta_minutes=None,
            courier_name=None,
            courier_phone=None,
            total_amount=Decimal("2100.00"),
            items=[
                OrderItemModel(
                    name="Бургер классик",
                    quantity=2,
                    price=Decimal("450.00"),
                    available=True,
                ),
                OrderItemModel(
                    name="Картофель фри",
                    quantity=2,
                    price=Decimal("200.00"),
                    available=False,
                ),
            ],
        ),
        OrderModel(
            id="ORD-1004",
            phone=DEMO_PHONE,
            status=OrderStatus.DELIVERED.value,
            address="Москва, ул. Тверская, 10, кв. 5",
            delivery_slot="вчера 19:00–21:00",
            eta_minutes=0,
            courier_name="Иван Петров",
            courier_phone="+79001112233",
            total_amount=Decimal("560.00"),
            items=[
                OrderItemModel(
                    name="Салат Цезарь",
                    quantity=1,
                    price=Decimal("560.00"),
                    available=True,
                ),
            ],
        ),
        OrderModel(
            id="ORD-1005",
            phone=DEMO_PHONE,
            status=OrderStatus.CONFIRMED.value,
            address="Москва, ул. Новый Арбат, 2",
            delivery_slot="сегодня 16:00–18:00",
            eta_minutes=120,
            courier_name=None,
            courier_phone=None,
            total_amount=Decimal("450.00"),
            items=[
                OrderItemModel(
                    name="Чизкейк",
                    quantity=1,
                    price=Decimal("450.00"),
                    available=True,
                ),
            ],
        ),
        # Многопозиционный оплаченный заказ для частичной отмены
        OrderModel(
            id="ORD-1006",
            phone=DEMO_PHONE,
            status=OrderStatus.PAID.value,
            address="Москва, ул. Покровка, 22",
            delivery_slot="сегодня 19:00–21:00",
            eta_minutes=80,
            courier_name=None,
            courier_phone=None,
            total_amount=Decimal("1540.00"),
            items=[
                OrderItemModel(
                    name="Пицца Пепперони",
                    quantity=1,
                    price=Decimal("790.00"),
                    available=True,
                ),
                OrderItemModel(
                    name="Салат Греческий",
                    quantity=1,
                    price=Decimal("450.00"),
                    available=True,
                ),
                OrderItemModel(
                    name="Лимонад 0.5л",
                    quantity=2,
                    price=Decimal("150.00"),
                    available=True,
                ),
            ],
        ),
    ]


async def seed_orders(session: AsyncSession) -> None:
    """Добавляет отсутствующие демо-заказы (не затирает уже изменённые)."""
    samples = _demo_orders()
    added = 0
    for sample in samples:
        exists = await session.get(OrderModel, sample.id)
        if exists is not None:
            continue
        session.add(sample)
        added += 1

    if added:
        await session.flush()
        logger.info("seed_orders_done", added=added, total=len(samples))
    else:
        logger.info("seed_orders_skipped", reason="all_present", total=len(samples))
