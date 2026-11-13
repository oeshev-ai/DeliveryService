"""Mock платёжный шлюз (доплата / возврат)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from redis.asyncio import Redis

from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PaymentResult:
    """Результат платёжной операции."""

    ok: bool
    payment_id: str
    amount: Decimal
    message: str


class MockPaymentGateway:
    """Идемпотентные mock-платежи в Redis."""

    def __init__(self, redis: Redis, *, key_prefix: str = "pay") -> None:
        self._redis = redis
        self._prefix = key_prefix

    def _idem_key(self, idempotency_key: str) -> str:
        return f"{self._prefix}:idem:{idempotency_key}"

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

        existing = await self._redis.get(self._idem_key(idempotency_key))
        if existing:
            logger.info(
                "payment_idempotent_hit",
                order_id=order_id,
                payment_id=existing,
            )
            return PaymentResult(
                ok=True,
                payment_id=str(existing),
                amount=amount,
                message="Платёж уже был выполнен ранее",
            )

        payment_id = f"pay_zero_{uuid4().hex[:8]}" if amount == 0 else f"pay_{uuid4().hex[:12]}"

        await self._redis.set(
            self._idem_key(idempotency_key),
            payment_id,
            ex=86_400,
        )
        logger.info(
            "payment_charged",
            order_id=order_id,
            payment_id=payment_id,
            amount=str(amount),
            description=description,
        )
        return PaymentResult(
            ok=True,
            payment_id=payment_id,
            amount=amount,
            message="Оплата прошла успешно" if amount > 0 else "Доплата не требуется",
        )

    async def refund(
        self,
        *,
        amount: Decimal,
        order_id: str,
        idempotency_key: str,
        description: str = "",
    ) -> PaymentResult:
        """Возврат средств (идемпотентный)."""
        if amount < 0:
            return PaymentResult(
                ok=False,
                payment_id="",
                amount=amount,
                message="Сумма возврата некорректна",
            )

        key = self._idem_key(f"refund:{idempotency_key}")
        existing = await self._redis.get(key)
        if existing:
            logger.info(
                "refund_idempotent_hit",
                order_id=order_id,
                refund_id=existing,
            )
            return PaymentResult(
                ok=True,
                payment_id=str(existing),
                amount=amount,
                message="Возврат уже был выполнен ранее",
            )

        refund_id = f"rfnd_zero_{uuid4().hex[:8]}" if amount == 0 else f"rfnd_{uuid4().hex[:12]}"

        await self._redis.set(key, refund_id, ex=86_400)
        logger.info(
            "payment_refunded",
            order_id=order_id,
            refund_id=refund_id,
            amount=str(amount),
            description=description,
        )
        return PaymentResult(
            ok=True,
            payment_id=refund_id,
            amount=amount,
            message=(f"Возврат {amount} ₽ оформлен" if amount > 0 else "Возврат не требуется"),
        )
