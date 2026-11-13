"""Тесты эскалации / mock CRM."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from delivery_bot.config import get_settings
from delivery_bot.db.session import (
    create_engine,
    create_session_factory,
    init_db,
    session_scope,
)
from delivery_bot.dialog.intents import Intent, IntentMatch
from delivery_bot.dialog.manager import DialogManager
from delivery_bot.dialog.session import DialogSession
from delivery_bot.dialog.states import DialogState
from delivery_bot.integrations.crm.repository import CrmRepository
from delivery_bot.integrations.crm.schemas import (
    CreateEscalationTicketRequest,
    EscalationTicketDTO,
)
from delivery_bot.services.escalation import EscalationService


def _match(intent: Intent) -> IntentMatch:
    return IntentMatch(intent=intent, confidence=1.0, source="keyword")


@pytest.mark.asyncio
async def test_operator_delegates_to_escalation() -> None:
    mgr = DialogManager()
    session = DialogSession(
        channel="telegram",
        user_id="42",
        consent_accepted=True,
        state=DialogState.MAIN_MENU,
    )
    resp = mgr.handle_intent(session, _match(Intent.OPERATOR))
    assert resp.delegate_escalation is True
    assert session.context.get("escalation_reason") == "operator"


@pytest.mark.asyncio
async def test_crm_repository_create_and_operator_reply() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    engine = create_engine(settings)
    await init_db(engine)
    factory = create_session_factory(engine)

    async with session_scope(factory) as session:
        repo = CrmRepository(session)
        ticket = await repo.create_ticket(
            channel="telegram",
            user_id="100",
            order_id="ORD-1004",
            reason="operator",
            transcript="Заказ: ORD-1004",
            initial_message="Нужна помощь с доставкой",
        )
        assert ticket.status == "open"
        assert len(ticket.messages) == 1

        op_msg = await repo.add_message(
            ticket.id,
            sender="operator",
            body="Здравствуйте, оператор на связи",
            delivered=False,
        )
        assert op_msg is not None
        assert op_msg.delivered is False

        pending = await repo.list_undelivered_operator_messages()
        assert any(m.id == op_msg.id for m, _ in pending)

        await repo.mark_delivered(op_msg.id)
        pending_after = await repo.list_undelivered_operator_messages()
        assert not any(m.id == op_msg.id for m, _ in pending_after)

    await engine.dispose()


@pytest.mark.asyncio
async def test_escalation_service_creates_ticket() -> None:
    crm = AsyncMock()
    crm.get_active_ticket.return_value = None
    crm.create_ticket.return_value = EscalationTicketDTO(
        id=7,
        channel="telegram",
        user_id="1",
        order_id="ORD-1004",
        reason="operator",
        status="open",
        transcript="Заказ: ORD-1004",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    service = EscalationService(crm)
    session = DialogSession(
        channel="telegram",
        user_id="1",
        consent_accepted=True,
        state=DialogState.ESCALATION_AWAITING_DESCRIPTION,
        context={"verified_order_id": "ORD-1004"},
    )
    resp = await service.handle_input(session, "Курьер не приехал")
    assert "7" in resp.text
    assert session.state == DialogState.OPERATOR_HANDOFF
    crm.create_ticket.assert_awaited_once()
    payload = crm.create_ticket.await_args.args[0]
    assert isinstance(payload, CreateEscalationTicketRequest)
    assert payload.initial_message == "Курьер не приехал"
