"""reminder_deliveries

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-24

Журнал напоминаний об истечении срока (app/reminders.py). Только новая таблица, существующие
данные не затрагиваются. Бэкап bot.db перед применением обязателен.
"""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'reminder_deliveries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=False),
        sa.Column('end_at', sa.DateTime(), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('error', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'subscription_id', 'end_at', 'kind', name='uq_reminder_deliveries_sub_end_kind'),
    )


def downgrade() -> None:
    op.drop_table('reminder_deliveries')
