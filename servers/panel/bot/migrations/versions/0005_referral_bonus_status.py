"""referral_bonuses: status (pending/granted/failed), target_end_at, granted_at nullable

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23

Бонус хранится до обращения к Panel (status=pending, target_end_at считается один раз),
повтор после сбоя выставляет ту же абсолютную дату. На 23.10.2026 таблица пуста: у
существующих строк (если появятся до деплоя) статус стал бы pending — перед применением
на боевой БД проверить SELECT count(*) FROM referral_bonuses. Бэкап bot.db обязателен.
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('referral_bonuses', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'status', sa.String(length=16), nullable=False, server_default='pending'))
        batch_op.add_column(sa.Column('target_end_at', sa.DateTime(), nullable=True))
        batch_op.alter_column('granted_at', existing_type=sa.DateTime(), nullable=True)


def downgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE referral_bonuses SET granted_at = CURRENT_TIMESTAMP WHERE granted_at IS NULL"
    ))
    with op.batch_alter_table('referral_bonuses', schema=None) as batch_op:
        batch_op.alter_column('granted_at', existing_type=sa.DateTime(), nullable=False)
        batch_op.drop_column('target_end_at')
        batch_op.drop_column('status')
