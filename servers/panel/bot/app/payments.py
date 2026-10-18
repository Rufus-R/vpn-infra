"""Платежи ЮKassa: создание заказа, обработка успеха/отмены, сверка.
См. docs/checkpoint-2026-10-17-payments.md, раздел 10 (схема A: вебхук + сверка).

Статусы payments (VARCHAR(16)): pending -> processing -> confirmed; paid_failed (деньги
получены, активация в Panel не удалась — повторяет сверка); canceled; expired (локально
закрыт по времени, поздний платёж всё равно обрабатывается); mismatch (ответ ЮKassa не
совпал с локальной строкой — разбирает админ).

Решение о деньгах принимается только по ответу GET /payments/{id}: тело вебхука не
подписано и ему не доверяем. Обработка одного платежа защищена _IN_FLIGHT (бот — один
процесс) и переходом статуса; активация идемпотентна (клиент с итоговым email уже на Panel
-> add_client не повторяется).
"""
from __future__ import annotations
import asyncio
import datetime as dt
import logging
import time

import httpx
from aiogram import Bot
from sqlalchemy import select

from app.config import ADMIN_IDS, REALITY_INBOUND_ID, SUB_BASE_URL, YOOKASSA_RETURN_URL
from app.db.base import async_session
from app.db.models import Payment, Plan, Receipt, Subscription, User
from app.panel_api import PanelApiClient, PanelApiError
from app.yookassa_api import YooKassaClient, YooKassaError, kopecks_from_amount

logger = logging.getLogger("payments")

REUSE_MAX_AGE = dt.timedelta(minutes=30)
NO_PROVIDER_ID_EXPIRE_AFTER = dt.timedelta(minutes=30)
PENDING_RECONCILE_AFTER = dt.timedelta(minutes=3)
PENDING_EXPIRE_AFTER = dt.timedelta(days=3)
RECONCILE_INTERVAL_SEC = 60

_CLAIMABLE = ("pending", "processing", "paid_failed", "expired")
_IN_FLIGHT: set[int] = set()


async def _notify(bot: Bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text)
    except Exception:
        logger.exception("не удалось отправить сообщение chat_id=%s", chat_id)


async def _notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        await _notify(bot, admin_id, text)


async def start_payment(tg_id: int, plan_id: int) -> str:
    """Вернуть ссылку на оплату тарифа. Свежий pending того же пользователя и тарифа
    переиспользуется (ссылка берётся GET-запросом к ЮKassa), иначе создаётся новый платёж."""
    if not YOOKASSA_RETURN_URL:
        raise YooKassaError("ЮKassa не настроена: задайте YOOKASSA_RETURN_URL")
    yk = YooKassaClient()
    try:
        async with async_session() as session:
            user = (await session.execute(
                select(User).where(User.tg_id == tg_id)
            )).scalar_one()
            plan = await session.get(Plan, plan_id)
            if plan is None or plan.price <= 0:
                raise ValueError("тариф недоступен для оплаты")
            reusable = (await session.execute(
                select(Payment)
                .join(Subscription, Payment.subscription_id == Subscription.id)
                .where(
                    Payment.user_id == user.id,
                    Payment.provider == "yookassa",
                    Payment.status == "pending",
                    Payment.provider_payment_id.is_not(None),
                    Payment.created_at > dt.datetime.utcnow() - REUSE_MAX_AGE,
                    Subscription.plan_id == plan.id,
                    Subscription.status == "pending_payment",
                )
                .order_by(Payment.id.desc())
                .limit(1)
            )).scalar_one_or_none()

        if reusable is not None:
            data = await yk.get_payment(reusable.provider_payment_id)
            url = (data.get("confirmation") or {}).get("confirmation_url")
            if data.get("status") == "pending" and url:
                return url

        return await _create_new(yk, user, plan)
    finally:
        await yk.close()


async def _create_new(yk: YooKassaClient, user: User, plan: Plan) -> str:
    now = dt.datetime.utcnow()
    async with async_session() as session:
        subscription = Subscription(
            user_id=user.id,
            panel_client_email=f"pending-tg{user.tg_id}-{int(time.time() * 1000)}@netru.bot",
            plan_id=plan.id,
            start_at=now,
            end_at=now + dt.timedelta(days=plan.duration_days),
            status="pending_payment",
        )
        session.add(subscription)
        await session.flush()
        payment = Payment(
            user_id=user.id, subscription_id=subscription.id, amount=plan.price,
            provider="yookassa", status="pending",
        )
        session.add(payment)
        await session.commit()
        local_id, subscription_id = payment.id, subscription.id

    try:
        data = await yk.create_payment(
            amount_kopecks=plan.price,
            description=f"Штиль: {plan.name}, {plan.duration_days} дн.",
            return_url=YOOKASSA_RETURN_URL,
            local_payment_id=local_id,
            idempotence_key=f"payment-{local_id}",
        )
    except YooKassaError as exc:
        # HTTP-ошибка (4xx/5xx): платёж у ЮKassa не создан — закрываем локально.
        # Сетевая ошибка/таймаут (status_code is None): платёж мог быть создан, строку не
        # трогаем — найдётся по metadata.payment_id, пустые pending чистит сверка.
        if exc.status_code is not None:
            await _abort_new(local_id, subscription_id)
        raise

    provider_id = data.get("id")
    url = (data.get("confirmation") or {}).get("confirmation_url")
    if not provider_id or not url:
        await _abort_new(local_id, subscription_id)
        raise YooKassaError("в ответе ЮKassa нет id платежа или confirmation_url")

    async with async_session() as session:
        payment = await session.get(Payment, local_id)
        payment.provider_payment_id = provider_id
        await session.commit()
    return url


async def _abort_new(payment_id: int, subscription_id: int) -> None:
    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        subscription = await session.get(Subscription, subscription_id)
        if payment is not None and payment.status == "pending" \
                and payment.provider_payment_id is None:
            payment.status = "canceled"
        if subscription is not None and subscription.status == "pending_payment":
            subscription.status = "rejected"
        await session.commit()


async def _find_local(provider_payment_id: str, data: dict) -> Payment | None:
    async with async_session() as session:
        payment = (await session.execute(
            select(Payment).where(Payment.provider_payment_id == provider_payment_id)
        )).scalar_one_or_none()
        if payment is not None:
            return payment
        raw_id = (data.get("metadata") or {}).get("payment_id")
        try:
            local_id = int(raw_id)
        except (TypeError, ValueError):
            return None
        payment = await session.get(Payment, local_id)
        if payment is None or payment.provider != "yookassa" \
                or payment.provider_payment_id is not None:
            return None
        payment.provider_payment_id = provider_payment_id
        await session.commit()
        return payment


async def process_payment_event(bot: Bot, provider_payment_id: str) -> None:
    """Обработать платёж по его id (из вебхука или сверки): GET -> проверка -> действие."""
    yk = YooKassaClient()
    try:
        data = await yk.get_payment(provider_payment_id)
    finally:
        await yk.close()

    local = await _find_local(provider_payment_id, data)
    if local is None:
        logger.warning("платёж %s не найден в локальной БД", provider_payment_id)
        return

    status = data.get("status")
    if status == "succeeded" and data.get("paid") is True:
        amount = data.get("amount") or {}
        meta_id = str((data.get("metadata") or {}).get("payment_id"))
        if (kopecks_from_amount(amount) != local.amount
                or amount.get("currency") != "RUB"
                or meta_id != str(local.id)):
            await _mark_mismatch(bot, local.id, provider_payment_id)
            return
        await _activate(bot, local.id)
    elif status == "canceled":
        await _mark_canceled(bot, local.id)


async def _mark_mismatch(bot: Bot, payment_id: int, provider_payment_id: str) -> None:
    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None or payment.status not in _CLAIMABLE:
            return
        payment.status = "mismatch"
        await session.commit()
    logger.error("payment %s: ответ ЮKassa не совпал с локальной строкой", payment_id)
    await _notify_admins(
        bot,
        f"⚠️ Платёж {payment_id} ({provider_payment_id}): сумма, валюта или metadata в "
        "ЮKassa не совпали с локальной записью. Подписка не выдана — требуется ручной разбор.",
    )


async def _mark_canceled(bot: Bot, payment_id: int) -> None:
    user_tg_id = None
    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None or payment.status not in ("pending", "expired"):
            return
        subscription = await session.get(Subscription, payment.subscription_id)
        user = await session.get(User, payment.user_id)
        payment.status = "canceled"
        if subscription is not None and subscription.status == "pending_payment":
            subscription.status = "rejected"
        user_tg_id = user.tg_id
        await session.commit()
    await _notify(bot, user_tg_id, "Платёж отменён, подписка не оформлена. "
                  "Если это ошибка — обратитесь в поддержку.")


async def _activate(bot: Bot, payment_id: int) -> None:
    if payment_id in _IN_FLIGHT:
        return
    _IN_FLIGHT.add(payment_id)
    try:
        await _activate_locked(bot, payment_id)
    finally:
        _IN_FLIGHT.discard(payment_id)


async def _activate_locked(bot: Bot, payment_id: int) -> None:
    sub_url = None
    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None or payment.status not in _CLAIMABLE:
            return
        previous_status = payment.status
        subscription = await session.get(Subscription, payment.subscription_id)
        plan = await session.get(Plan, subscription.plan_id)
        user = await session.get(User, payment.user_id)
        payment.status = "processing"
        await session.commit()

        email = f"tg{user.tg_id}-sub{subscription.id}@netru.bot"
        now = dt.datetime.utcnow()
        end_at = now + dt.timedelta(days=plan.duration_days)

        panel = PanelApiClient()
        try:
            if REALITY_INBOUND_ID is None:
                raise PanelApiError("REALITY_INBOUND_ID не задан")
            if not await panel.client_exists(email):
                await panel.add_client(
                    email=email,
                    limit_ip=plan.device_count,
                    total_gb=0,
                    expiry_time_ms=int(end_at.timestamp() * 1000),
                    inbound_ids=[REALITY_INBOUND_ID],
                    tg_id=user.tg_id,
                    comment=f"bot:paid:sub{subscription.id}",
                )
            client = (await panel.get_client(email))["client"]
        except (PanelApiError, httpx.HTTPError) as exc:
            payment.status = "paid_failed"
            await session.commit()
            logger.error("payment %s: активация в Panel не удалась: %s", payment_id, exc)
            if previous_status != "paid_failed":
                await _notify_admins(
                    bot,
                    f"⚠️ Платёж {payment_id} оплачен, но подписку создать не удалось "
                    f"({exc}). Сверка повторит попытку автоматически.",
                )
            return
        finally:
            await panel.close()

        sub_id = client.get("subId")
        if sub_id and SUB_BASE_URL:
            sub_url = f"{SUB_BASE_URL}{sub_id}"
        subscription.panel_client_email = email
        subscription.panel_client_uuid = client.get("uuid")
        subscription.panel_client_sub_id = sub_id
        subscription.inbound_ids = [REALITY_INBOUND_ID]
        subscription.start_at = now
        subscription.end_at = end_at
        subscription.status = "active"
        payment.status = "confirmed"
        has_receipt = (await session.execute(
            select(Receipt.id).where(Receipt.payment_id == payment.id)
        )).scalar_one_or_none()
        if has_receipt is None:
            session.add(Receipt(
                payment_id=payment.id, status="pending_review",
                amount=payment.amount, service_name=plan.name,
            ))
        await session.commit()
        user_tg_id, plan_name, amount_rub = user.tg_id, plan.name, payment.amount // 100

    if sub_url:
        text = f"Оплата получена, подписка активна.\n\nСсылка на подписку:\n{sub_url}"
    else:
        text = ("Оплата получена, подписка создана, но ссылку сформировать "
                "автоматически не удалось. Обратитесь в поддержку.")
    await _notify(bot, user_tg_id, text)
    await _notify_admins(
        bot,
        f"✅ Платёж {payment_id} подтверждён: «{plan_name}», {amount_rub} ₽. "
        "Чек: черновик создан (pending_review), выпуск пока вручную.",
    )


async def reconcile_once(bot: Bot) -> None:
    now = dt.datetime.utcnow()
    to_check: list[str] = []
    async with async_session() as session:
        rows = (await session.execute(
            select(Payment).where(
                Payment.provider == "yookassa",
                Payment.status.in_(("pending", "processing", "paid_failed")),
            )
        )).scalars().all()
        for payment in rows:
            age = now - payment.created_at
            if payment.status == "pending":
                if payment.provider_payment_id is None:
                    if age > NO_PROVIDER_ID_EXPIRE_AFTER:
                        await _expire(session, payment)
                    continue
                if age > PENDING_EXPIRE_AFTER:
                    await _expire(session, payment)
                    continue
                if age < PENDING_RECONCILE_AFTER:
                    continue
            if payment.provider_payment_id is not None:
                to_check.append(payment.provider_payment_id)
        await session.commit()

    for provider_payment_id in to_check:
        try:
            await process_payment_event(bot, provider_payment_id)
        except Exception:
            logger.exception("сверка: ошибка по платежу %s", provider_payment_id)


async def _expire(session, payment: Payment) -> None:
    payment.status = "expired"
    subscription = await session.get(Subscription, payment.subscription_id)
    if subscription is not None and subscription.status == "pending_payment":
        subscription.status = "rejected"


async def reconcile_loop(bot: Bot) -> None:
    while True:
        try:
            await reconcile_once(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("сверка платежей: сбой цикла")
        await asyncio.sleep(RECONCILE_INTERVAL_SEC)
