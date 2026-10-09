"""Начальные данные для dev-режима (до появления Alembic-миграций с seed-данными).
Тарифы синхронизированы с docs/commercial/tariffs.md и лендингом (/root/commercial-legal/
на S1, вне git) — при изменении цен поправить оба места."""
from sqlalchemy import select
from app.db.base import async_session
from app.db.models import Plan

TRIAL_PLAN_NAME = "Пробный период"

# (name, duration_days, device_count, price_rub, discount_pct, description)
_PAID_PLANS = [
    ("Штиль Бриз · Личный борт", 30, 2, 200, None,
     "Месяц ровного соединения для ваших основных устройств — телефона и ноутбука. "
     "Хороший способ познакомиться с сервисом без длинных обязательств."),
    ("Штиль Бриз · Общая палуба", 30, 5, 250, None,
     "Месяц спокойного доступа сразу для 5 устройств — удобно попробовать всей семьёй "
     "или компанией."),
    ("Штиль Прилив · Личный борт", 90, 2, 500, 17,
     "Три месяца стабильного соединения для двух устройств. Оптимально, если пользуетесь "
     "сервисом регулярно, но не хотите оформлять на год."),
    ("Штиль Прилив · Общая палуба", 90, 5, 650, 13,
     "Три месяца ровного доступа на 5 устройств — одна подписка на всех близких."),
    ("Штиль Фарватер · Личный борт", 365, 2, 1800, 25,
     "Год спокойного, стабильного доступа для ваших устройств. Самый выгодный вариант "
     "для личного пользования."),
    ("Штиль Фарватер · Общая палуба", 365, 5, 2250, 25,
     "Год безмятежного доступа для всей семьи — до 5 устройств одновременно, без "
     "необходимости продлевать вручную."),
]


async def seed_defaults() -> None:
    async with async_session() as session:
        result = await session.execute(select(Plan).where(Plan.name == TRIAL_PLAN_NAME))
        if result.scalar_one_or_none() is None:
            session.add(Plan(
                name=TRIAL_PLAN_NAME,
                duration_days=7,
                device_count=1,
                price=0,
                discount_pct=None,
                description="7 дней бесплатно, 1 устройство — для знакомства с сервисом.",
            ))

        for name, duration_days, device_count, price_rub, discount_pct, description in _PAID_PLANS:
            exists = await session.execute(select(Plan).where(Plan.name == name))
            if exists.scalar_one_or_none() is None:
                session.add(Plan(
                    name=name,
                    duration_days=duration_days,
                    device_count=device_count,
                    price=price_rub * 100,
                    discount_pct=discount_pct,
                    description=description,
                ))

        await session.commit()
