"""Mock платёжный шлюз (доплата / возврат)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from redis.asyncio import Redis

from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)

_IDEMPOTENCY_TTL = 86_400
_AMOUNT_CONFLICT_MSG = "ключ идемпотентности уже использован с другой суммой"


@dataclass(frozen=True, slots=True)
class PaymentResult:
    """Результат платёжной операции."""

    ok: bool
    payment_id: str
    amount: Decimal
    message: str


class MockPaymentGateway:
    """Идемпотентные mock-платежи в Redis (SET NX + JSON payload)."""

    def __init__(self, redis: Redis, *, key_prefix: str = "pay") -> None:
        self._redis = redis
        self._prefix = key_prefix

    def _idem_key(self, idempotency_key: str) -> str:
        return f"{self._prefix}:idem:{idempotency_key}"

    async def _idempotent_op(
        self,
        *,
        key: str,
        amount: Decimal,
        order_id: str,
        payment_id: str,
        success_message: str,
        replay_message: str,
        log_event: str,
        description: str,
    ) -> PaymentResult:
        """SET NX с JSON; конфликт суммы → отказ; истечение ключа → один retry."""
        payload = json.dumps({"payment_id": payment_id, "amount": str(amount)})
        for _attempt in range(2):
            created = await self._redis.set(key, payload, nx=True, ex=_IDEMPOTENCY_TTL)
            if created:
                logger.info(
                    log_event,
                    order_id=order_id,
                    payment_id=payment_id,
                    amount=str(amount),
                    description=description,
                )
                return PaymentResult(
                    ok=True,
                    payment_id=payment_id,
                    amount=amount,
                    message=success_message,
                )

            existing_raw = await self._redis.get(key)
            if existing_raw is None:
                # Ключ истёк между SET NX и GET — повторяем один раз.
                continue
            try:
                existing = json.loads(str(existing_raw))
                existing_amount = Decimal(str(existing["amount"]))
                existing_id = str(existing["payment_id"])
            except (json.JSONDecodeError, KeyError, TypeError):
                # Legacy: раньше хранили только payment_id строкой.
                existing_id = str(existing_raw)
                existing_amount = amount

            if existing_amount != amount:
                logger.info(
                    "payment_idempotent_amount_conflict",
                    order_id=order_id,
                    key=key,
                )
                return PaymentResult(
                    ok=False,
                    payment_id=existing_id,
                    amount=amount,
                    message=_AMOUNT_CONFLICT_MSG,
                )
            logger.info(
                "payment_idempotent_hit",
                order_id=order_id,
                payment_id=existing_id,
            )
            return PaymentResult(
                ok=True,
                payment_id=existing_id,
                amount=amount,
                message=replay_message,
            )

        # После retry ключ снова исчез — создаём новый платёж без NX-гонки.
        await self._redis.set(key, payload, ex=_IDEMPOTENCY_TTL)
        logger.info(
            log_event,
            order_id=order_id,
            payment_id=payment_id,
            amount=str(amount),
            description=description,
        )
        return PaymentResult(
            ok=True,
            payment_id=payment_id,
            amount=amount,
            message=success_message,
        )

    async def charge(
        self,
        *,
        amount: Decimal,
        order_id: str,
        idempotency_key: str,
        description: str = "",
    ) -> PaymentResult:
        """Списывает доплату (или no-op при amount=0)."""
        if amount < 0:
            return PaymentResult(
                ok=False,
                payment_id="",
                amount=amount,
                message="Сумма платежа некорректна",
            )

        payment_id = f"pay_zero_{uuid4().hex[:8]}" if amount == 0 else f"pay_{uuid4().hex[:12]}"
        return await self._idempotent_op(
            key=self._idem_key(idempotency_key),
            amount=amount,
            order_id=order_id,
            payment_id=payment_id,
            success_message=("Оплата прошла успешно" if amount > 0 else "Доплата не требуется"),
            replay_message="Платёж уже был выполнен ранее",
            log_event="payment_charged",
            description=description,
        )

    async def refund(
        self,
        *,
        amount: Decimal,
        order_id: str,
        idempotency_key: str,
        description: str = "",
    ) -> PaymentResult:
        """Возврат средств (идемпотентный через SET NX)."""
        if amount < 0:
            return PaymentResult(
                ok=False,
                payment_id="",
                amount=amount,
                message="Сумма возврата некорректна",
            )

        refund_id = f"rfnd_zero_{uuid4().hex[:8]}" if amount == 0 else f"rfnd_{uuid4().hex[:12]}"
        return await self._idempotent_op(
            key=self._idem_key(f"refund:{idempotency_key}"),
            amount=amount,
            order_id=order_id,
            payment_id=refund_id,
            success_message=(
                f"Возврат {amount} ₽ оформлен" if amount > 0 else "Возврат не требуется"
            ),
            replay_message="Возврат уже был выполнен ранее",
            log_event="payment_refunded",
            description=description,
        )
