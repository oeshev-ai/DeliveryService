"""Сценарий статуса заказа: верификация order_id + last4."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from delivery_bot.dialog import texts
from delivery_bot.dialog.keyboards import (
    is_telegram_webapp_url,
    main_menu_keyboard,
    order_list_keyboard,
    order_status_keyboard,
)
from delivery_bot.dialog.limits import AttemptLimiter
from delivery_bot.dialog.manager import DialogResponse
from delivery_bot.dialog.session import DialogSession
from delivery_bot.dialog.states import DialogState
from delivery_bot.integrations.oms.cache import OrderStatusCache
from delivery_bot.integrations.oms.client import OmsClient, OmsError
from delivery_bot.logging_setup import get_logger
from delivery_bot.observability.metrics import inc_verify_attempt
from delivery_bot.services.status_formatter import (
    format_order_status,
    format_orders_list,
    format_public_status,
)
from delivery_bot.webapp.bindings import WebAppBindingStore

if TYPE_CHECKING:
    from delivery_bot.services.review import ReviewService

logger = get_logger(__name__)

VERIFY_SCOPE = "verify"
_ORDER_ID_RE = re.compile(r"^(ORD-)?(\d{3,})$", re.IGNORECASE)


class OrderStatusService:
    """Диалоговый сценарий «Статус заказа»."""

    def __init__(
        self,
        oms: OmsClient,
        cache: OrderStatusCache,
        limiter: AttemptLimiter,
        *,
        bindings: WebAppBindingStore | None = None,
        webapp_url: str | None = None,
        review_service: ReviewService | None = None,
    ) -> None:
        self._oms = oms
        self._cache = cache
        self._limiter = limiter
        self._bindings = bindings
        self._webapp_url = webapp_url
        self._review = review_service

    def _limit_subject(self, session: DialogSession) -> str:
        return f"{session.channel}:{session.user_id}"

    def _status_markup(self, order_id: str):
        return order_status_keyboard(order_id, webapp_url=self._webapp_url)

    def _status_footer(self) -> str:
        if is_telegram_webapp_url(self._webapp_url):
            return "\n\nМожно открыть виджет статуса в Mini App 👇"
        return (
            "\n\nВиджет Mini App доступен после настройки "
            "<code>TELEGRAM_WEBAPP_URL</code> на HTTPS (ngrok/tunnel)."
        )

    async def _grant_webapp_access(
        self, session: DialogSession, order_id: str, phone_last4: str
    ) -> None:
        if self._bindings is None:
            return
        await self._bindings.grant(
            session.user_id,
            order_id=order_id,
            phone_last4=phone_last4,
        )

    async def start(self, session: DialogSession) -> DialogResponse:
        """Старт сценария статуса."""
        verified_id = session.context.get("verified_order_id")
        if verified_id:
            return await self._show_order(session, str(verified_id))

        session.state = DialogState.AWAITING_ORDER_ID
        session.context.pop("pending_order_id", None)
        return DialogResponse(
            text=(
                "Чтобы показать статус, нужен номер заказа "
                "(например <code>ORD-1001</code> или <code>1001</code>)."
            ),
        )

    async def handle_input(self, session: DialogSession, text: str) -> DialogResponse:
        """Обработка ввода в состояниях ожидания order_id / last4."""
        if session.state == DialogState.AWAITING_ORDER_ID:
            return await self._on_order_id(session, text)
        if session.state == DialogState.AWAITING_PHONE_LAST4:
            return await self._on_last4(session, text)
        return await self.start(session)

    async def select_order(self, session: DialogSession, order_id: str) -> DialogResponse:
        """Выбор заказа из списка (callback).

        Если телефон уже подтверждён в этой сессии (список «другие заказы»),
        повторный ввод last4 не нужен.
        """
        oid = order_id.strip().upper()
        last4 = session.context.get("phone_last4")
        if last4:
            session.context["verified_order_id"] = oid
            session.context.pop("pending_order_id", None)
            return await self._show_order(session, oid)

        session.context["pending_order_id"] = oid
        session.state = DialogState.AWAITING_PHONE_LAST4
        return DialogResponse(
            text=(
                f"Заказ <b>{oid}</b>. "
                "Введите последние 4 цифры телефона, указанного при оформлении."
            ),
        )

    async def _on_order_id(self, session: DialogSession, text: str) -> DialogResponse:
        order_id = _normalize_order_id(text)
        if not order_id:
            return DialogResponse(
                text="Не распознал номер заказа. Пример: <code>ORD-1001</code>.",
            )

        session.context["pending_order_id"] = order_id

        try:
            public = await self._oms.get_public(order_id)
        except OmsError:
            session.state = DialogState.AWAITING_PHONE_LAST4
            return DialogResponse(
                text=(
                    "Сервис заказов временно недоступен. "
                    "Можете сразу ввести последние 4 цифры телефона — "
                    "попробуем ещё раз, либо напишите «оператор»."
                ),
            )

        if public is None:
            session.context.pop("pending_order_id", None)
            session.state = DialogState.MAIN_MENU
            return DialogResponse(
                text="Заказ не найден. Проверьте номер или выберите действие в меню.",
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )

        session.state = DialogState.AWAITING_PHONE_LAST4
        return DialogResponse(
            text=(
                f"{format_public_status(public.id, public.in_transit)}\n\n"
                "Введите последние 4 цифры телефона:"
            ),
        )

    async def _on_last4(self, session: DialogSession, text: str) -> DialogResponse:
        subject = self._limit_subject(session)
        check = await self._limiter.check(VERIFY_SCOPE, subject)
        if not check.allowed:
            session.state = DialogState.MAIN_MENU
            return DialogResponse(
                text=texts.format_blocked(check.blocked_seconds_remaining),
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )

        last4 = "".join(ch for ch in text.strip() if ch.isdigit())
        if len(last4) != 4:
            return DialogResponse(text="Нужны ровно 4 цифры. Попробуйте ещё раз.")

        order_id = session.context.get("pending_order_id")
        if not order_id:
            session.state = DialogState.AWAITING_ORDER_ID
            return DialogResponse(text="Сначала пришлите номер заказа.")

        try:
            result = await self._oms.verify(str(order_id), last4)
        except OmsError:
            cached = await self._cache.get(str(order_id))
            if cached and cached.phone_last4 == last4:
                session.context["verified_order_id"] = cached.id
                session.context["phone_last4"] = last4
                session.state = DialogState.ORDER_STATUS
                await self._grant_webapp_access(session, cached.id, last4)
                return DialogResponse(
                    text=(
                        "OMS недоступен, показываю последний известный статус из кэша:\n\n"
                        + format_order_status(cached)
                    ),
                    reply_markup=self._status_markup(cached.id),
                )
            return DialogResponse(
                text=(
                    "Не удалось проверить заказ — сервис временно недоступен. "
                    "Попробуйте позже или напишите «оператор»."
                ),
                reply_markup=main_menu_keyboard(),
            )

        if not result.ok or result.order is None:
            inc_verify_attempt(success=False)
            hit = await self._limiter.hit(VERIFY_SCOPE, subject)
            if hit.is_blocked:
                session.state = DialogState.MAIN_MENU
                session.context.pop("pending_order_id", None)
                return DialogResponse(
                    text=texts.format_blocked(hit.blocked_seconds_remaining),
                    reply_markup=main_menu_keyboard(),
                )
            left = hit.max_attempts - hit.attempts
            return DialogResponse(
                text=(
                    "Не удалось подтвердить заказ (номер или телефон не совпали). "
                    f"Осталось попыток: {left}."
                ),
            )

        await self._limiter.reset(VERIFY_SCOPE, subject)
        inc_verify_attempt(success=True)
        order = result.order
        await self._cache.set(order)
        session.context["verified_order_id"] = order.id
        session.context["phone_last4"] = last4
        session.context.pop("pending_order_id", None)
        session.state = DialogState.ORDER_STATUS
        await self._grant_webapp_access(session, order.id, last4)

        try:
            siblings = await self._oms.list_by_last4(last4)
            others = [s for s in siblings if s.id != order.id]
            if others:
                extras_note = "\n\nДругие заказы с этим телефоном:\n" + format_orders_list(siblings)
                return await self._with_review_offer(
                    session,
                    order.id,
                    DialogResponse(
                        text=format_order_status(order) + extras_note,
                        reply_markup=order_list_keyboard(
                            [s.id for s in siblings],
                            active_order_id=order.id,
                            webapp_url=self._webapp_url,
                        ),
                    ),
                )
        except OmsError:
            logger.info("oms_list_skipped_after_verify", order_id=order.id)

        return await self._with_review_offer(
            session,
            order.id,
            DialogResponse(
                text=format_order_status(order) + self._status_footer(),
                reply_markup=self._status_markup(order.id),
            ),
        )

    async def _with_review_offer(
        self,
        session: DialogSession,
        order_id: str,
        response: DialogResponse,
    ) -> DialogResponse:
        if self._review is None:
            return response
        offer = await self._review.offer_for_order(session, order_id)
        if offer is None:
            return response
        return DialogResponse(
            text=response.text + "\n\n" + offer.text,
            reply_markup=offer.reply_markup or response.reply_markup,
        )

    async def _show_order(self, session: DialogSession, order_id: str) -> DialogResponse:
        cached = await self._cache.get(order_id)
        if cached is not None:
            session.state = DialogState.ORDER_STATUS
            last4 = session.context.get("phone_last4")
            if last4:
                await self._grant_webapp_access(session, cached.id, str(last4))
            return await self._with_review_offer(
                session,
                cached.id,
                DialogResponse(
                    text=format_order_status(cached) + self._status_footer(),
                    reply_markup=self._status_markup(cached.id),
                ),
            )

        last4 = session.context.get("phone_last4")
        if last4:
            try:
                result = await self._oms.verify(order_id, str(last4))
                if result.ok and result.order:
                    await self._cache.set(result.order)
                    session.state = DialogState.ORDER_STATUS
                    await self._grant_webapp_access(session, result.order.id, str(last4))
                    return await self._with_review_offer(
                        session,
                        result.order.id,
                        DialogResponse(
                            text=format_order_status(result.order) + self._status_footer(),
                            reply_markup=self._status_markup(result.order.id),
                        ),
                    )
            except OmsError:
                pass

        session.context["pending_order_id"] = order_id
        session.state = DialogState.AWAITING_PHONE_LAST4
        return DialogResponse(
            text=(f"Для заказа <b>{order_id}</b> подтвердите последние 4 цифры телефона."),
        )


def _normalize_order_id(text: str) -> str | None:
    raw = text.strip().upper().replace(" ", "")
    match = _ORDER_ID_RE.match(raw)
    if not match:
        if raw.startswith("ORD-") and raw[4:].isdigit():
            return raw
        return None
    num = match.group(2)
    return f"ORD-{num}"
