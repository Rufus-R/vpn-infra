"""broadcasts, broadcast_deliveries

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-24

Рассылка сервисных сообщений (app/broadcast.py). Только новые таблицы, существующие
данные не затрагиваются. Бэкап bot.db перед применением обязателен.
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'broadcasts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('audience', sa.String(length=32), nullable=False),
        sa.Column('body', sa.String(length=4096), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'broadcast_deliveries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('broadcast_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('error', sa.String(length=255), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['broadcast_id'], ['broadcasts.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'broadcast_id', 'user_id', name='uq_broadcast_deliveries_broadcast_user'),
    )


def downgrade() -> None:
    op.drop_table('broadcast_deliveries')
    op.drop_table('broadcasts')
