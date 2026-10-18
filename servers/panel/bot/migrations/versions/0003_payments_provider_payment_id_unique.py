"""payments: unique index on provider_payment_id

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-18
"""
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'uq_payments_provider_payment_id',
        'payments',
        ['provider_payment_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_payments_provider_payment_id', table_name='payments')
