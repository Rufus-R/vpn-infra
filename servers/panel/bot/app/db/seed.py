"""Начальные данные для dev-режима (до появления Alembic-миграций с seed-данными)."""
from sqlalchemy import select
from app.db.base import async_session
from app.db.models import Plan

TRIAL_PLAN_NAME = "Пробный период"


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
            ))
            await session.commit()
