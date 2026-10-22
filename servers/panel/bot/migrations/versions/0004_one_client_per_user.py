"""one client per user: payments.plan_id/target_end_at, subscriptions UNIQUE(user_id) и
next_device_*, plans.referral_bonus_days, linked_clients, UNIQUE(referral_bonuses.referred_id),
переименование тарифов (без префикса «Штиль», «месяц» -> «30 дней»)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-22

Перед применением на боевой БД таблица subscriptions должна быть очищена (UNIQUE(user_id)),
бэкап bot.db — обязателен (docs/checkpoint-2026-10-22-subscriptions.md).
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

# (старое имя, новое имя, новое описание)
_RENAMES = [
    ("Штиль Бриз · Личный борт", "Бриз · Личный борт",
     "30 дней ровного соединения для ваших основных устройств — телефона и ноутбука. "
     "Хороший способ познакомиться с сервисом без длинных обязательств."),
    ("Штиль Бриз · Общая палуба", "Бриз · Общая палуба",
     "30 дней спокойного доступа сразу для 5 устройств — удобно попробовать всей семьёй "
     "или компанией."),
    ("Штиль Прилив · Личный борт", "Прилив · Личный борт",
     "90 дней стабильного соединения для двух устройств. Оптимально, если пользуетесь "
     "сервисом регулярно, но не хотите оформлять на год."),
    ("Штиль Прилив · Общая палуба", "Прилив · Общая палуба",
     "90 дней ровного доступа на 5 устройств — одна подписка на всех близких."),
    ("Штиль Фарватер · Личный борт", "Фарватер · Личный борт",
     "365 дней спокойного, стабильного доступа для ваших устройств. Самый выгодный вариант "
     "для личного пользования."),
    ("Штиль Фарватер · Общая палуба", "Фарватер · Общая палуба",
     "365 дней безмятежного доступа для всей семьи — до 5 устройств одновременно."),
]
# длительность тарифа (дни) -> бонус рефереру (дни)
_BONUS_BY_DURATION = {30: 7, 90: 14, 365: 30}


def upgrade() -> None:
    conn = op.get_bind()

    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'referral_bonus_days', sa.Integer(), nullable=False, server_default='0'))
    for duration, bonus in _BONUS_BY_DURATION.items():
        conn.execute(
            sa.text("UPDATE plans SET referral_bonus_days = :b WHERE duration_days = :d AND price > 0"),
            {"b": bonus, "d": duration},
        )
    for old, new, description in _RENAMES:
        conn.execute(
            sa.text("UPDATE plans SET name = :new, description = :desc WHERE name = :old"),
            {"new": new, "desc": description, "old": old},
        )

    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('plan_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('target_end_at', sa.DateTime(), nullable=True))
        batch_op.create_foreign_key('fk_payments_plan_id_plans', 'plans', ['plan_id'], ['id'])
    conn.execute(sa.text(
        "UPDATE payments SET plan_id = (SELECT s.plan_id FROM subscriptions s "
        "WHERE s.id = payments.subscription_id) WHERE plan_id IS NULL"
    ))

    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('next_device_count', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('next_device_at', sa.DateTime(), nullable=True))
        batch_op.create_unique_constraint('uq_subscriptions_user_id', ['user_id'])

    with op.batch_alter_table('referral_bonuses', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_referral_bonuses_referred_id', ['referred_id'])

    op.create_table(
        'linked_clients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('panel_client_email', sa.String(length=128), nullable=False),
        sa.Column('label', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'panel_client_email', name='uq_linked_clients_user_email'),
    )


def downgrade() -> None:
    conn = op.get_bind()
    op.drop_table('linked_clients')

    with op.batch_alter_table('referral_bonuses', schema=None) as batch_op:
        batch_op.drop_constraint('uq_referral_bonuses_referred_id', type_='unique')

    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_constraint('uq_subscriptions_user_id', type_='unique')
        batch_op.drop_column('next_device_at')
        batch_op.drop_column('next_device_count')

    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_payments_plan_id_plans', type_='foreignkey')
        batch_op.drop_column('target_end_at')
        batch_op.drop_column('plan_id')

    # Имена возвращаются, описания — нет (прежний текст в миграции не хранится).
    for old, new, _description in _RENAMES:
        conn.execute(sa.text("UPDATE plans SET name = :old WHERE name = :new"),
                     {"old": old, "new": new})
    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.drop_column('referral_bonus_days')
