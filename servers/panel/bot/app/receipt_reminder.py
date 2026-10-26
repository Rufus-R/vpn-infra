"""Напоминание админам о чеках в pending_review старше суток.

Решение оператора 20.10.2026 (часть схемы чеков «Мой налог»); подключено 27.10.2026
после запуска боевого магазина ЮKassa — см. checkpoint-2026-10-26-go-live.md, Этап 4.

Правило: раз в час в окне 10:00–22:00 МСК бот перечитывает receipts со статусом
pending_review, созданные более 24 часов назад, и уведомляет админов списком.
Повтор о том же чеке — не чаще раза в сутки ({receipt_id: дата МСК} в памяти
процесса; после рестарта бота возможен один повтор — принято, как у состояния
проверки токена в app/nalog.py).
"""
import asyncio
import datetime as dt
import logging

from aiogram import Bot
from sqlalchemy import select

from app import timeutil
from app.db.base import async_session
from app.db.models import Payment, Receipt, User
from app.receipts import _notify_admins

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SEC = 3600
STALE_AFTER = dt.timedelta(hours=24)
MSK_FMT = "%d.%m.%Y %H:%M"
# Окно напоминаний: 10:00 <= час МСК < 22:00
WINDOW_START_HOUR = 10
WINDOW_END_HOUR = 22

_last_notified: dict[int, dt.date] = {}


def _now_msk() -> dt.datetime:
    """Текущее aware-время МСК (в БД наивный UTC, сервер — UTC)."""
    return timeutil.to_msk(dt.datetime.utcnow())


async def run_once(bot: Bot) -> int:
    """Один проход: уведомить админов о чеках, по которым напоминание сегодня ещё
    не отправлялось. Возвращает число напомянутых чеков."""
    cutoff = dt.datetime.utcnow() - STALE_AFTER
    today = _now_msk().date()
    async with async_session() as session:
        rows = (await session.execute(
            select(Receipt)
            .where(Receipt.status == "pending_review")
            .where(Receipt.created_at < cutoff)
            .order_by(Receipt.id)
        )).scalars().all()
        stale: list[tuple[Receipt, User | None]] = []
        for receipt in rows:
            if _last_notified.get(receipt.id) == today:
                continue
            user = (await session.execute(
                select(User).join(Payment, Payment.user_id == User.id).where(
                    Payment.id == receipt.payment_id
                )
            )).scalar_one_or_none()
            stale.append((receipt, user))

    if not stale:
        return 0

    lines = [f"⏰ Чеков в pending_review старше суток: {len(stale)}"]
    for receipt, user in stale:
        who = str(user.tg_id) if user else "?"
        if user and user.username:
            who = f"{who} (@{user.username})"
        lines.append(
            f"• #{receipt.id} · {receipt.service_name} · {receipt.amount / 100:.0f} ₽ · "
            f"от {who}, {timeutil.fmt_msk(receipt.created_at, MSK_FMT)}"
        )
    lines.append("Выдать: «🛠 Админ» → «Чеки к выдаче».")

    await _notify_admins(bot, "\n".join(lines))
    for receipt, _ in stale:
        _last_notified[receipt.id] = today
    return len(stale)


async def receipt_reminder_loop(bot: Bot) -> None:
    logger.info("цикл напоминаний о чеках запущен (интервал %s c)", CHECK_INTERVAL_SEC)
    while True:
        try:
            hour = _now_msk().hour
            if WINDOW_START_HOUR <= hour < WINDOW_END_HOUR:
                await run_once(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("напоминания о чеках: сбой прохода")
        await asyncio.sleep(CHECK_INTERVAL_SEC)
