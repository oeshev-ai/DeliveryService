"""Сценарий «Курьер» / трекинг."""

from __future__ import annotations

from delivery_bot.dialog.manager import DialogResponse
from delivery_bot.dialog.session import DialogSession
from delivery_bot.dialog.states import DialogState
from delivery_bot.dialog.keyboards import (
    is_telegram_webapp_url,
    main_menu_keyboard,
    order_status_keyboard,
)
from delivery_bot.integrations.oms.cache import OrderStatusCache
from delivery_bot.integrations.oms.client import OmsClient, OmsError
from delivery_bot.integrations.tms.mock import MockTmsService
from delivery_bot.logging_setup import get_logger
from delivery_bot.services.status_formatter import status_badge

logger = get_logger(__name__)


class CourierService:
    """Показ данных курьера после верификации заказа."""

    def __init__(
        self,
        oms: OmsClient,
        cache: OrderStatusCache,
        tms: MockTmsService,
        *,
        webapp_url: str | None = None,
    ) -> None:
        self._oms = oms
        self._cache = cache
        self._tms = tms
        self._webapp_url = webapp_url

    async def show(self, session: DialogSession) -> DialogResponse:
        order_id = session.context.get("verified_order_id")
        if not order_id:
            session.state = DialogState.AWAITING_ORDER_ID
            return DialogResponse(
                text=(
                    "Сначала подтвердим заказ: пришлите номер "
                    "(например <code>ORD-1001</code>), затем last4 телефона.\n"
                    "После этого смогу показать курьера и карту."
                ),
            )

        order = await self._cache.get(str(order_id))
        if order is None:
            last4 = session.context.get("phone_last4")
            if last4:
                try:
                    result = await self._oms.verify(str(order_id), str(last4))
                    if result.ok and result.order:
                        order = result.order
                        await self._cache.set(order)
                except OmsError:
                    logger.warning("courier_oms_unavailable", order_id=order_id)

        if order is None:
            return DialogResponse(
                text=(
                    "Не удалось загрузить заказ. Откройте «Статус заказа» "
                    "и подтвердите его ещё раз."
                ),
                reply_markup=main_menu_keyboard(),
            )

        point = self._tms.tracking_for(
            order_id=order.id,
            status=order.status,
            courier_name=order.courier_name,
            courier_phone=order.courier_phone,
            eta_minutes=order.eta_minutes,
        )

        lines = [
            f"Заказ <b>{order.id}</b>",
            f"Статус: {status_badge(order.status)}",
        ]
        if point.courier_name:
            lines.append(f"Курьер: <b>{point.courier_name}</b>")
            if point.courier_phone:
                lines.append(f"Телефон: {point.courier_phone}")
        else:
            lines.append("Курьер ещё не назначен.")

        if point.eta_minutes is not None and order.status not in {"delivered", "cancelled"}:
            lines.append(f"ETA: ≈ {point.eta_minutes} мин")

        if point.gps_available:
            lines.append("Геолокация курьера доступна на карте в Mini App.")
        elif point.message:
            lines.append(point.message)

        if is_telegram_webapp_url(self._webapp_url):
            lines.append("\nОткройте карту трекинга 👇")
        else:
            lines.append(
                "\nКарта в Mini App — после HTTPS "
                "<code>TELEGRAM_WEBAPP_URL</code>."
            )

        session.state = DialogState.ORDER_STATUS
        return DialogResponse(
            text="\n".join(lines),
            reply_markup=order_status_keyboard(
                order.id,
                webapp_url=self._webapp_url,
                open_map=True,
            ),
        )
