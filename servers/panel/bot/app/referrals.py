"""Реферальные бонусы (docs/checkpoint-2026-10-23-live-payment-test.md, «План рефералки»).

Бонус за приглашённого начисляется один раз — при его первой оплате. Запись ReferralBonus
(status=pending) создаётся в той же транзакции, что подтверждает платёж (payments.py);
дата окончания (target_end_at) считается ОДИН раз и сохраняется до обращения к Panel, поэтому
повтор после сбоя не прибавляет срок дважды. Применение идёт после выхода из блокировки
приглашённого и под блокировкой реферера (две блокировки одновременно не держим).

Статусы: pending (ждёт применения или повтора сверкой) -> granted; failed — разбирает админ
(бессрочный клиент реферера, нет реферера или тарифа «Пробный период»). Вернуть в повтор:
UPDATE referral_bonuses SET status='pending' WHERE id=...

Реферер без клиента получает клиента по тарифу «Пробный период» (лимит 1 устройство);
существующему клиенту срок увеличивается, лимит и название тарифа не меняются.
"""
from __future__ import annotations
import asyncio
import datetime as dt
import logging

import httpx
from aiogram import Bot
from sqlalchemy import func, select

from app.config import ADMIN_IDS
from app.db.base import async_session
from app.db.models import Payment, Plan, ReferralBonus, User
from app.db.seed import TRIAL_PLAN_NAME
from app.panel_api import PanelApiClient, PanelApiError
from app.subscription_service import (
    UnlimitedClientError, apply_period, compute_target_end, save_subscription, user_lock,
)
from app.timeutil import fmt_msk

logger = logging.getLogger("referrals")


async def _notify(bot: Bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text)
    except Exception:
        logger.exception("не удалось отправить сообщение chat_id=%s", chat_id)


async def _notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        await _notify(bot, admin_id, text)


async def create_pending_bonus(session, user: User, plan: Plan, payment: Payment) -> int | None:
    """Создать запись бонуса (pending) в транзакции вызывающего; коммит — на нём.
    Возвращает id записи или None, если бонус не положен."""
    if user.referrer_id is None or plan.referral_bonus_days <= 0:
        return None
    exists = (await session.execute(
        select(ReferralBonus.id).where(ReferralBonus.referred_id == user.id)
    )).scalar_one_or_none()
    if exists is not None:
        return None
    earlier = (await session.execute(
        select(func.count()).select_from(Payment).where(
            Payment.user_id == user.id,
            Payment.status == "confirmed",
            Payment.id != payment.id,
        )
    )).scalar_one()
    if earlier:
        return None
    bonus = ReferralBonus(
        referrer_id=user.referrer_id, referred_id=user.id,
        bonus_days=plan.referral_bonus_days, status="pending",
    )
    session.add(bonus)
    await session.flush()
    return bonus.id


async def apply_bonus(bot: Bot, bonus_id: int) -> None:
    """Применить бонус к клиенту реферера. Не бросает исключений: сбой платёжного потока
    из-за бонуса недопустим, повтор сделает сверка."""
    try:
        async with async_session() as session:
            bonus = await session.get(ReferralBonus, bonus_id)
            if bonus is None or bonus.status != "pending":
                return
            referrer_id = bonus.referrer_id
        async with user_lock(referrer_id):
            await _apply_in_lock(bot, bonus_id)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("реферальный бонус %s: необработанный сбой", bonus_id)


async def _apply_in_lock(bot: Bot, bonus_id: int) -> None:
    async with async_session() as session:
        bonus = await session.get(ReferralBonus, bonus_id)
        if bonus is None or bonus.status != "pending":
            return
        referrer = await session.get(User, bonus.referrer_id)
        plan = (await session.execute(
            select(Plan).where(Plan.name == TRIAL_PLAN_NAME)
        )).scalar_one_or_none()
        if referrer is None or plan is None:
            bonus.status = "failed"
            await session.commit()
            logger.error("бонус %s: нет реферера или тарифа «%s»", bonus_id, TRIAL_PLAN_NAME)
            await _notify_admins(
                bot,
                f"⚠️ Реферальный бонус {bonus_id}: не найден реферер или тариф "
                f"«{TRIAL_PLAN_NAME}». Бонус не начислен — требуется ручной разбор.",
            )
            return

        panel = PanelApiClient()
        try:
            if bonus.target_end_at is None:
                # Считается один раз и сохраняется ДО вызова Panel.
                bonus.target_end_at = await compute_target_end(
                    panel, referrer.tg_id, bonus.bonus_days)
                await session.commit()
            target = bonus.target_end_at
            result = await apply_period(
                panel, user=referrer, plan=plan, target_end_at=target, kind="trial")
        except UnlimitedClientError as exc:
            bonus.status = "failed"
            await session.commit()
            logger.error("бонус %s: %s", bonus_id, exc)
            await _notify_admins(
                bot,
                f"⚠️ Реферальный бонус {bonus_id} (реферер user_id={bonus.referrer_id}): "
                "клиент бессрочный, срок автоматически не меняется. Бонус не начислен.",
            )
            return
        except (PanelApiError, httpx.HTTPError) as exc:
            logger.error("бонус %s: сбой Panel, повтор сверкой: %s", bonus_id, exc)
            return
        finally:
            await panel.close()

        await save_subscription(session, referrer, plan, result, target, "trial")
        referrer_tg_id, days = referrer.tg_id, bonus.bonus_days
        sub_url, created = result.sub_url, result.created
        bonus.status = "granted"
        bonus.granted_at = dt.datetime.utcnow()
        await session.commit()

    text = (f"🎁 Ваш приглашённый оформил подписку — вам начислено {days} дн. "
            f"Срок действует до {fmt_msk(target)} (МСК).")
    if created and sub_url:
        text += f"\n\nСсылка на подписку:\n{sub_url}"
    await _notify(bot, referrer_tg_id, text)
    logger.info("бонус %s начислен: %s дн., реферер tg_id=%s", bonus_id, days, referrer_tg_id)


async def retry_pending_bonuses(bot: Bot) -> None:
    """Повторить применение всех pending-бонусов (вызывается из reconcile_loop)."""
    async with async_session() as session:
        ids = (await session.execute(
            select(ReferralBonus.id)
            .where(ReferralBonus.status == "pending")
            .order_by(ReferralBonus.id)
        )).scalars().all()
    for bonus_id in ids:
        await apply_bonus(bot, bonus_id)
