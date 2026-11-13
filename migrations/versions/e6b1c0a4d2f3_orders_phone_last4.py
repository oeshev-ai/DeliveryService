"""orders phone_last4 generated column

Revision ID: e6b1c0a4d2f3
Revises: 48a5fd403aa1
Create Date: 2026-11-13 17:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6b1c0a4d2f3"
down_revision: str | Sequence[str] | None = "48a5fd403aa1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Хранимая last4 и индекс под фильтр списка заказов."""
    op.add_column(
        "orders",
        sa.Column(
            "phone_last4",
            sa.String(length=4),
            sa.Computed(
                "right(regexp_replace(phone, '[^0-9]', '', 'g'), 4)",
                persisted=True,
            ),
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_orders_phone_last4"), "orders", ["phone_last4"], unique=False)


def downgrade() -> None:
    """Убирает индекс и колонку phone_last4."""
    op.drop_index(op.f("ix_orders_phone_last4"), table_name="orders")
    op.drop_column("orders", "phone_last4")
