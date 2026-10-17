"""receipts: чеки НПД по платежам

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('receipts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('payment_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('service_name', sa.String(length=255), nullable=False),
    sa.Column('receipt_uuid', sa.String(length=64), nullable=True),
    sa.Column('receipt_url', sa.String(length=255), nullable=True),
    sa.Column('error', sa.String(length=512), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('sent_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('payment_id')
    )


def downgrade() -> None:
    op.drop_table('receipts')
