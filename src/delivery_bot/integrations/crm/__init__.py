"""Mock CRM integration."""

from delivery_bot.integrations.crm.client import CrmClient, CrmError
from delivery_bot.integrations.crm.schemas import (
    CreateEscalationTicketRequest,
    EscalationTicketDTO,
)

__all__ = [
    "CrmClient",
    "CrmError",
    "CreateEscalationTicketRequest",
    "EscalationTicketDTO",
]
