"""Рассылка сервисных сообщений пользователям (миграция 0006, 24.10.2026).

Только сервисные сообщения (пробный период, срок подписки, изменения условий): согласие на
ПДн рекламную рассылку не покрывает. Получатели — только с privacy_accepted; всегда
исключены привязанные ручные клиенты (linked_clients) и администраторы (ADMIN_IDS).

Получатели фиксируются снимком в broadcast_deliveries при запуске (draft -> sending условным
UPDATE, двойной запуск невозможен). Отправка идёт фоновой задачей, по одному сообщению с
паузой. Перед запросом в Telegram доставка получает статус sending; если бот перезапущен
в этот момент, при старте такие строки становятся unknown и не повторяются (возможен
дубль хуже пропуска). Интерфейс — app/handlers/broadcast.py.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import NamedTuple

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import func, select, update

from app.config import ADMIN_IDS
from app.db.base import async_session
from app.db.models import Broadcast, BroadcastDelivery, LinkedClient, Subscription, User

logger = logging.getLogger("broadcast")

AUDIENCES = {
    "nosub": "Без подписки и пробного периода",
    "expiring": "Срок подписки заканчивается в ближайшие 3 дня",
}
EXPIRING_WINDOW = dt.timedelta(days=3)
SEND_PAUSE_SEC = 0.1
MAX_RETRY_AFTER_ATTEMPTS = 3

_RUNNING: set[int] = set()
_TASKS: set[asyncio.Task] = set()


class BroadcastInfo(NamedTuple):
    audience: str
    body: str
    status: str


def _audience_query(audience: str):
    now = dt.datetime.utcnow()
    query = select(User.id).where(
        User.privacy_accepted.is_(True),
        User.tg_id.not_in(ADMIN_IDS),
        ~select(LinkedClient.id).where(LinkedClient.user_id == User.id).exists(),
    )
    if audience == "nosub":
        query = query.where(
            User.trial_used.is_(False),
            ~select(Subscription.id).where(Subscription.user_id == User.id).exists(),
        )
    elif audience == "expiring":
        query = query.where(
            select(Subscription.id).where(
                Subscription.user_id == User.id,
                Subscription.status.in_(("active", "trial")),
                Subscription.end_at > now,
                Subscription.end_at <= now + EXPIRING_WINDOW,
            ).exists()
        )
    else:
        raise ValueError(f"неизвестная аудитория: {audience}")
    return query.order_by(User.id)


async def audience_user_ids(session, audience: str) -> list[int]:
    return list((await session.execute(_audience_query(audience))).scalars().all())


async def create_draft(admin_tg_id: int, audience: str, body: str) -> int:
    async with async_session() as session:
        row = Broadcast(audience=audience, body=body, status="draft", created_by=admin_tg_id)
        session.add(row)
        await session.flush()
        broadcast_id = row.id
        await session.commit()
    return broadcast_id


async def set_draft_body(broadcast_id: int, body: str) -> bool:
    async with async_session() as session:
        result = await session.execute(
            update(Broadcast)
            .where(Broadcast.id == broadcast_id, Broadcast.status == "draft")
            .values(body=body)
        )
        await session.commit()
        return result.rowcount == 1


async def cancel_draft(broadcast_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(
            update(Broadcast)
            .where(Broadcast.id == broadcast_id, Broadcast.status == "draft")
            .values(status="cancelled", finished_at=dt.datetime.utcnow())
        )
        await session.commit()
        return result.rowcount == 1


async def get_broadcast(broadcast_id: int) -> BroadcastInfo | None:
    async with async_session() as session:
        row = (await session.execute(
            select(Broadcast.audience, Broadcast.body, Broadcast.status)
            .where(Broadcast.id == broadcast_id))).first()
    return BroadcastInfo(*row) if row else None


async def start_broadcast(broadcast_id: int) -> int | None:
    """draft -> sending и снимок получателей одной транзакцией. None — рассылка не в
    состоянии draft (уже запущена или отменена); иначе число получателей."""
    now = dt.datetime.utcnow()
    async with async_session() as session:
        claimed = await session.execute(
            update(Broadcast)
            .where(Broadcast.id == broadcast_id, Broadcast.status == "draft")
            .values(status="sending", started_at=now)
        )
        if claimed.rowcount != 1:
            await session.rollback()
            return None
        audience = (await session.execute(
            select(Broadcast.audience).where(Broadcast.id == broadcast_id))).scalar_one()
        user_ids = await audience_user_ids(session, audience)
        session.add_all(
            BroadcastDelivery(broadcast_id=broadcast_id, user_id=uid) for uid in user_ids)
        if not user_ids:
            await session.execute(
                update(Broadcast).where(Broadcast.id == broadcast_id)
                .values(status="done", finished_at=now))
        await session.commit()
    return len(user_ids)


async def _send_one(bot: Bot, tg_id: int, body: str) -> tuple[str, str | None]:
    for _ in range(MAX_RETRY_AFTER_ATTEMPTS):
        try:
            await bot.send_message(tg_id, body)
            return "sent", None
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
        except TelegramForbiddenError:
            return "blocked", None
        except Exception as exc:
            logger.exception("не удалось отправить рассылку tg_id=%s", tg_id)
            return "failed", f"{type(exc).__name__}: {exc}"[:255]
    return "failed", "TelegramRetryAfter: исчерпан лимит повторов"


async def _finish(bot: Bot, broadcast_id: int) -> None:
    async with async_session() as session:
        rows = (await session.execute(
            select(BroadcastDelivery.status, func.count())
            .where(BroadcastDelivery.broadcast_id == broadcast_id)
            .group_by(BroadcastDelivery.status))).all()
        created_by = (await session.execute(
            select(Broadcast.created_by).where(Broadcast.id == broadcast_id))).scalar_one()
        closed = await session.execute(
            update(Broadcast)
            .where(Broadcast.id == broadcast_id, Broadcast.status == "sending")
            .values(status="done", finished_at=dt.datetime.utcnow()))
        await session.commit()
    if closed.rowcount != 1:
        return
    counts = {status: count for status, count in rows}
    total = sum(counts.values())
    text = (
        f"📣 Рассылка #{broadcast_id} завершена: из {total} отправлено "
        f"{counts.get('sent', 0)}, бот заблокирован {counts.get('blocked', 0)}, "
        f"ошибок {counts.get('failed', 0)}, итог неизвестен {counts.get('unknown', 0)}."
    )
    try:
        await bot.send_message(created_by, text)
    except Exception:
        logger.exception("не удалось отправить отчёт о рассылке #%s", broadcast_id)


async def run_broadcast(bot: Bot, broadcast_id: int) -> None:
    if broadcast_id in _RUNNING:
        return
    _RUNNING.add(broadcast_id)
    try:
        while True:
            async with async_session() as session:
                row = (await session.execute(
                    select(BroadcastDelivery.id, User.tg_id, Broadcast.body)
                    .join(User, User.id == BroadcastDelivery.user_id)
                    .join(Broadcast, Broadcast.id == BroadcastDelivery.broadcast_id)
                    .where(BroadcastDelivery.broadcast_id == broadcast_id,
                           BroadcastDelivery.status == "pending")
                    .order_by(BroadcastDelivery.id).limit(1))).first()
                if row is None:
                    break
                delivery_id, tg_id, body = row
                await session.execute(
                    update(BroadcastDelivery).where(BroadcastDelivery.id == delivery_id)
                    .values(status="sending"))
                await session.commit()
            status, error = await _send_one(bot, tg_id, body)
            async with async_session() as session:
                await session.execute(
                    update(BroadcastDelivery).where(BroadcastDelivery.id == delivery_id)
                    .values(status=status, error=error,
                            sent_at=dt.datetime.utcnow() if status == "sent" else None))
                await session.commit()
            await asyncio.sleep(SEND_PAUSE_SEC)
        await _finish(bot, broadcast_id)
    except Exception:
        logger.exception("сбой рассылки #%s", broadcast_id)
    finally:
        _RUNNING.discard(broadcast_id)


def start_send(bot: Bot, broadcast_id: int) -> None:
    task = asyncio.create_task(run_broadcast(bot, broadcast_id))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


async def resume_broadcasts(bot: Bot) -> None:
    """Вызывается один раз при старте бота: дошлёт pending-доставки прерванных рассылок;
    доставки в состоянии sending (итог неизвестен) становятся unknown и не повторяются."""
    try:
        async with async_session() as session:
            ids = list((await session.execute(
                select(Broadcast.id).where(Broadcast.status == "sending"))).scalars().all())
            if ids:
                await session.execute(
                    update(BroadcastDelivery)
                    .where(BroadcastDelivery.broadcast_id.in_(ids),
                           BroadcastDelivery.status == "sending")
                    .values(status="unknown", error="бот перезапущен во время отправки"))
                await session.commit()
        for broadcast_id in ids:
            start_send(bot, broadcast_id)
    except Exception:
        logger.exception("не удалось возобновить рассылки")
