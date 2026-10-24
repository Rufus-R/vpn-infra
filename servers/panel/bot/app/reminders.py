"""Напоминания об истечении пробного периода и подписки (оферта п. 4.5, миграция 0007).

Правило: напоминание «через 3 дня» и «завтра» по календарным дням МСК — разница между датой
окончания и сегодняшней датой (МСК) равна 3 или 1. Отправка только в окне 10:00–12:00 МСК
(для любой точки России это не раньше 09:00 и не позже 21:00 по местному времени); если бот в
10:00–11:00 не работал, напоминание досылается до 12:00, после — пропускается.

Получатели — как у рассылки: с согласием на ПДн, без linked_clients и ADMIN_IDS; подписки
в статусах trial/active. Перед отправкой срок сверяется с Panel (источник истины): отключённый
или бессрочный клиент и расхождение вида напоминания пропускаются, при недоступности Panel
повтор на следующей минуте окна.

Журнал reminder_deliveries с UNIQUE(subscription_id, end_at, kind) исключает повтор. Строка
со статусом sending создаётся до запроса в Telegram; после рестарта такие строки становятся
unknown и не повторяются (дубль хуже пропуска). Статус failed тоже не повторяется.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import NamedTuple

import httpx
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.config import ADMIN_IDS
from app.db.base import async_session
from app.db.models import LinkedClient, ReminderDelivery, Subscription, User
from app.panel_api import PanelApiClient, PanelApiError
from app.timeutil import fmt_msk, to_msk

logger = logging.getLogger("reminders")

WINDOW_START_HOUR_MSK = 10
WINDOW_END_HOUR_MSK = 12  # не включая: отправка до 12:00 МСК
CHECK_INTERVAL_SEC = 60
SEND_PAUSE_SEC = 0.1
MAX_RETRY_AFTER_ATTEMPTS = 3
CANDIDATE_HORIZON = dt.timedelta(days=5)

_DAYS_TO_KIND = {3: "3d", 1: "1d"}
_KIND_PHRASE = {"3d": "через 3 дня", "1d": "завтра"}


class Candidate(NamedTuple):
    sub_id: int
    email: str
    status: str
    end_at: dt.datetime
    user_id: int
    tg_id: int


def in_window(now: dt.datetime) -> bool:
    """now — наивный UTC. Окно отправки: 10:00 <= час МСК < 12:00."""
    return WINDOW_START_HOUR_MSK <= to_msk(now).hour < WINDOW_END_HOUR_MSK


def reminder_kind(end_at: dt.datetime, now: dt.datetime) -> str | None:
    """Вид напоминания ('3d' / '1d') или None. Обе даты — наивный UTC."""
    if end_at <= now:
        return None
    days = (to_msk(end_at).date() - to_msk(now).date()).days
    return _DAYS_TO_KIND.get(days)


def _trunc(value: dt.datetime) -> dt.datetime:
    return value.replace(microsecond=0)


def _from_ms(ms: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).replace(tzinfo=None)


def build_message(kind: str, status: str,
                  end_at: dt.datetime) -> tuple[str, InlineKeyboardMarkup]:
    when = _KIND_PHRASE[kind]
    until = fmt_msk(end_at, "%d.%m.%Y %H:%M")
    if status == "trial":
        text = (f"Ваш пробный период заканчивается {when}, {until} (МСК). "
                "Чтобы не остаться без VPN, выберите тариф.")
        button = "💳 Выбрать тариф"
    else:
        text = (f"Ваша подписка заканчивается {when}, {until} (МСК). "
                "Продлите её, чтобы не потерять доступ: новый срок прибавится к текущему.")
        button = "💳 Продлить"
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button, callback_data="menu:tariffs")],
    ])
    return text, markup


async def _candidates(now: dt.datetime) -> list[Candidate]:
    async with async_session() as session:
        rows = (await session.execute(
            select(Subscription.id, Subscription.panel_client_email, Subscription.status,
                   Subscription.end_at, User.id, User.tg_id)
            .join(User, User.id == Subscription.user_id)
            .where(
                User.privacy_accepted.is_(True),
                User.tg_id.not_in(ADMIN_IDS),
                ~select(LinkedClient.id).where(LinkedClient.user_id == User.id).exists(),
                Subscription.status.in_(("active", "trial")),
                Subscription.end_at > now,
                Subscription.end_at <= now + CANDIDATE_HORIZON,
            )
            .order_by(Subscription.id))).all()
    return [Candidate(*row) for row in rows]


async def _unsent(candidates: list[Candidate],
                  now: dt.datetime) -> list[tuple[Candidate, str]]:
    planned = []
    for cand in candidates:
        kind = reminder_kind(cand.end_at, now)
        if kind is not None:
            planned.append((cand, kind))
    if not planned:
        return []
    async with async_session() as session:
        rows = (await session.execute(
            select(ReminderDelivery.subscription_id, ReminderDelivery.kind,
                   ReminderDelivery.end_at)
            .where(ReminderDelivery.subscription_id.in_([c.sub_id for c, _ in planned])))).all()
    done = {(sub_id, kind, end_at) for sub_id, kind, end_at in rows}
    return [(c, k) for c, k in planned if (c.sub_id, k, _trunc(c.end_at)) not in done]


async def _panel_end(panel: PanelApiClient, email: str) -> dt.datetime | None:
    """Срок клиента на Panel (наивный UTC) или None, если клиент отключён или бессрочный."""
    client = (await panel.get_client(email))["client"]
    if not client.get("enable", False):
        return None
    expiry_ms = int(client.get("expiryTime") or 0)
    if expiry_ms <= 0:
        return None
    return _from_ms(expiry_ms)


async def _claim(sub_id: int, end_at: dt.datetime, kind: str) -> int | None:
    """Записать доставку со статусом sending. None — такое напоминание уже есть."""
    async with async_session() as session:
        row = ReminderDelivery(
            subscription_id=sub_id, end_at=_trunc(end_at), kind=kind, status="sending")
        session.add(row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        return row.id


async def _finish_delivery(delivery_id: int, status: str, error: str | None) -> None:
    async with async_session() as session:
        await session.execute(
            update(ReminderDelivery).where(ReminderDelivery.id == delivery_id)
            .values(status=status, error=error,
                    sent_at=dt.datetime.utcnow() if status == "sent" else None))
        await session.commit()


async def _send(bot: Bot, tg_id: int, text: str,
                markup: InlineKeyboardMarkup) -> tuple[str, str | None]:
    for _ in range(MAX_RETRY_AFTER_ATTEMPTS):
        try:
            await bot.send_message(tg_id, text, reply_markup=markup)
            return "sent", None
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
        except TelegramForbiddenError:
            return "blocked", None
        except Exception as exc:
            logger.exception("не удалось отправить напоминание tg_id=%s", tg_id)
            return "failed", f"{type(exc).__name__}: {exc}"[:255]
    return "failed", "TelegramRetryAfter: исчерпан лимит повторов"


async def run_once(bot: Bot, now: dt.datetime) -> dict[str, int]:
    """Одна проверка: отправить все положенные напоминания. Окно времени проверяет вызывающий
    (reminder_loop). Возвращает число доставок по статусам."""
    counts: dict[str, int] = {}
    due = await _unsent(await _candidates(now), now)
    if not due:
        return counts
    panel = PanelApiClient()
    try:
        for cand, kind in due:
            try:
                panel_end = await _panel_end(panel, cand.email)
            except (PanelApiError, httpx.HTTPError):
                logger.warning("напоминание: Panel недоступна для подписки %s", cand.sub_id)
                continue
            if panel_end is None or reminder_kind(panel_end, now) != kind:
                continue
            delivery_id = await _claim(cand.sub_id, panel_end, kind)
            if delivery_id is None:
                continue
            text, markup = build_message(kind, cand.status, panel_end)
            status, error = await _send(bot, cand.tg_id, text, markup)
            await _finish_delivery(delivery_id, status, error)
            counts[status] = counts.get(status, 0) + 1
            await asyncio.sleep(SEND_PAUSE_SEC)
    finally:
        await panel.close()
    if counts:
        logger.info("напоминания об истечении: %s", counts)
    return counts


async def mark_interrupted() -> None:
    """При старте бота: доставки в состоянии sending (итог неизвестен) становятся unknown."""
    async with async_session() as session:
        await session.execute(
            update(ReminderDelivery)
            .where(ReminderDelivery.status == "sending")
            .values(status="unknown", error="бот перезапущен во время отправки"))
        await session.commit()


async def reminder_loop(bot: Bot) -> None:
    try:
        await mark_interrupted()
    except Exception:
        logger.exception("напоминания: не удалось обработать прерванные доставки")
    while True:
        try:
            now = dt.datetime.utcnow()
            if in_window(now):
                await run_once(bot, now)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("напоминания об истечении: сбой цикла")
        await asyncio.sleep(CHECK_INTERVAL_SEC)
