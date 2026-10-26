"""Выпуск чеков самозанятого из бота (патч №3, 26.10.2026).

См. docs/checkpoint-2026-10-26-receipts.md. Статусы receipts (свободная строка, VARCHAR(16)):
pending_review -> sending -> sent | failed | unknown; итог retry (запрос заведомо не ушёл)
возвращает чек в pending_review; unknown и failed админ возвращает в очередь вручную.
Переход pending_review -> sending - один UPDATE с проверкой числа строк и commit до обращения
к «Мой налог»: второй админ или повторное нажатие чек не захватят. POST /income не
идемпотентен, поэтому любое сомнение - unknown, автоповтора нет. При старте бота sending
становится unknown (mark_interrupted), как у напоминаний.
Выпуск включается флагом NALOG_ISSUE_ENABLED (по умолчанию выключен): тестовый платёж ЮKassa
не должен стать настоящим доходом в «Мой налог».
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

from aiogram import Bot
from sqlalchemy import func, select, update

from app import nalog
from app.config import ADMIN_IDS, NALOG_ISSUE_ENABLED
from app.db.base import async_session
from app.db.models import Payment, Receipt, User

logger = logging.getLogger("receipts")

ACTIVE_STATUSES = ("pending_review", "sending", "unknown", "failed")
STATUS_LABELS = {
    "pending_review": "ждёт выдачи",
    "sending": "выпускается",
    "sent": "выпущен",
    "failed": "ошибка, чек не создан",
    "unknown": "результат неизвестен",
}


@dataclass
class ReceiptCard:
    id: int
    payment_id: int
    status: str
    amount: int
    service_name: str
    receipt_url: str | None
    error: str | None
    created_at: dt.datetime
    sent_at: dt.datetime | None


def _card(receipt: Receipt) -> ReceiptCard:
    return ReceiptCard(
        id=receipt.id, payment_id=receipt.payment_id, status=receipt.status,
        amount=receipt.amount, service_name=receipt.service_name,
        receipt_url=receipt.receipt_url, error=receipt.error,
        created_at=receipt.created_at, sent_at=receipt.sent_at,
    )


def issuing_enabled() -> bool:
    return bool(NALOG_ISSUE_ENABLED) and nalog.nalog_enabled()


async def load_card(receipt_id: int) -> ReceiptCard | None:
    async with async_session() as session:
        receipt = await session.get(Receipt, receipt_id)
        return _card(receipt) if receipt is not None else None


async def list_active(limit: int) -> tuple[int, list[ReceiptCard]]:
    async with async_session() as session:
        total = (await session.execute(
            select(func.count(Receipt.id)).where(Receipt.status.in_(ACTIVE_STATUSES))
        )).scalar_one()
        rows = (await session.execute(
            select(Receipt).where(Receipt.status.in_(ACTIVE_STATUSES))
            .order_by(Receipt.id).limit(limit)
        )).scalars().all()
    return total, [_card(r) for r in rows]


async def _transition(receipt_id: int, allowed: tuple[str, ...], **values) -> bool:
    """Атомарно сменить поля чека, только если его статус входит в allowed."""
    async with async_session() as session:
        result = await session.execute(
            update(Receipt)
            .where(Receipt.id == receipt_id, Receipt.status.in_(allowed))
            .values(**values))
        await session.commit()
    return result.rowcount == 1


async def mark_interrupted() -> None:
    """При старте бота: чеки в состоянии sending (итог неизвестен) становятся unknown."""
    async with async_session() as session:
        await session.execute(
            update(Receipt)
            .where(Receipt.status == "sending")
            .values(status="unknown", error="бот перезапущен во время выпуска"))
        await session.commit()


async def requeue(receipt_id: int) -> bool:
    return await _transition(receipt_id, ("unknown", "failed"), status="pending_review")


async def confirm_manual(receipt_id: int) -> bool:
    """Админ проверил приложение: чек по неизвестной попытке там есть. Ссылки у нас нет."""
    return await _transition(
        receipt_id, ("unknown",), status="sent", sent_at=dt.datetime.utcnow(),
        error="подтверждено админом вручную: чек есть в приложении")


async def _notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            logger.exception("не удалось отправить сообщение admin_id=%s", admin_id)


async def issue(bot: Bot, receipt_id: int) -> str:
    """Выпустить чек. Итог: disabled / not_claimed / sent / failed / unknown / retry."""
    if not issuing_enabled():
        return "disabled"
    if not await _transition(receipt_id, ("pending_review",), status="sending", error=None):
        return "not_claimed"

    async with async_session() as session:
        row = (await session.execute(
            select(Receipt, User).select_from(Receipt)
            .join(Payment, Receipt.payment_id == Payment.id)
            .join(User, Payment.user_id == User.id)
            .where(Receipt.id == receipt_id)
        )).one_or_none()
    if row is None:
        await _transition(receipt_id, ("sending",), status="failed",
                          error="платёж или пользователь не найдены")
        return "failed"
    receipt, user = row
    service_name, amount = receipt.service_name, receipt.amount
    operation_time, user_tg_id = receipt.created_at, user.tg_id

    try:
        result = await nalog.issue_receipt(service_name, amount, operation_time)
    except Exception as exc:
        logger.exception("чек #%s: непредвиденная ошибка при выпуске", receipt_id)
        result = nalog.IssueResult(
            "unknown", error=f"непредвиденная ошибка: {type(exc).__name__}")

    logger.info("чек #%s: итог %s, receipt_uuid=%s",
                receipt_id, result.status, result.receipt_uuid)
    outcome = result.status if result.status in ("sent", "failed", "retry") else "unknown"
    if outcome == "sent":
        values = dict(status="sent", receipt_uuid=result.receipt_uuid,
                      receipt_url=result.receipt_url, sent_at=dt.datetime.utcnow(),
                      error=None)
    elif outcome == "retry":
        values = dict(status="pending_review", error=result.error)
    else:
        values = dict(status=outcome, error=result.error)
    if not await _transition(receipt_id, ("sending",), **values):
        logger.error("чек #%s: итог %s не записан (статус уже не sending)",
                     receipt_id, outcome)

    rub = amount // 100
    if outcome == "sent":
        if result.receipt_url:
            try:
                await bot.send_message(
                    user_tg_id,
                    f"🧾 Чек по вашей оплате «{service_name}», {rub} ₽:\n{result.receipt_url}")
                note = "ссылка отправлена пользователю"
            except Exception:
                logger.exception("чек #%s: не удалось отправить ссылку пользователю", receipt_id)
                note = "ссылку пользователю отправить не удалось"
        else:
            note = "ссылки нет (ИНН не определён), пользователю ничего не отправлено"
        await _notify_admins(
            bot, f"✅ Чек #{receipt_id} выпущен ({rub} ₽, {service_name}); {note}.")
    elif outcome == "unknown":
        await _notify_admins(
            bot,
            f"⚠️ Чек #{receipt_id} ({rub} ₽): результат запроса к «Мой налог» неизвестен. "
            "Проверьте приложение (раздел «Продажи») и решите в админ-меню: «Чек есть в "
            f"приложении» или «Вернуть в очередь». Причина: {result.error}")
    elif outcome == "failed":
        await _notify_admins(
            bot,
            f"❌ Чек #{receipt_id} ({rub} ₽): ФНС отказала, чек не создан. "
            f"Причина: {result.error}")
    return outcome
