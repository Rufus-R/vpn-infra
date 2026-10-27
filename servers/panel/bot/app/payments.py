"""Платежи ЮKassa: создание заказа, обработка успеха/отмены, сверка.
См. docs/checkpoint-2026-10-17-payments.md, раздел 10 (схема A: вебхук + сверка).

Статусы payments (VARCHAR(16)): pending -> processing -> confirmed; paid_failed (деньги
получены, активация в Panel не удалась — повторяет сверка); canceled; expired (локально
закрыт по времени, поздний платёж всё равно обрабатывается); mismatch (ответ ЮKassa не
совпал с локальной строкой — разбирает админ).

С 22.10.2026 (миграция 0004): заказ создаёт только строку Payment с plan_id (строки
Subscription больше нет: одна подписка и один клиент Panel на пользователя, см.
app/subscription_service.py). Целевая дата окончания (payments.target_end_at) считается ОДИН
раз при захвате платежа и сохраняется до обращения к Panel — повтор после сбоя выставит ту же
абсолютную дату, срок не прибавится дважды. Новая покупка при действующей подписке — продление.

Решение о деньгах принимается только по ответу GET /payments/{id}: тело вебхука не
подписано и ему не доверяем. Обработка одного платежа защищена _IN_FLIGHT (бот — один
процесс), блокировкой пользователя и переходом статуса.
"""
from __future__ import annotations
import asyncio
import datetime as dt
import logging

import httpx
from aiogram import Bot
from sqlalchemy import select

from app.config import (
    ADMIN_IDS, YOOKASSA_RETURN_URL, YOOKASSA_SECRET_KEY_FILE, YOOKASSA_SHOP_ID,
    YOOKASSA_WEBHOOK_SECRET,
)
from app.db.base import async_session
from app.db.models import Payment, Plan, Receipt, User
from app.panel_api import PanelApiClient, PanelApiError
from app.receipts import issue as issue_receipt, issuing_enabled as _receipts_enabled
from app.subscription_service import (
    apply_due_downgrades, apply_period, compute_target_end, save_subscription, user_lock,
)
from app.referrals import apply_bonus, create_pending_bonus, retry_pending_bonuses
from app.timeutil import fmt_msk
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
    переиспользуется (ссылка берётся GET-запросом к ЮKassa), иначе создаётся новый платёж.
    Действующая подписка не мешает: оплата продлевает срок."""
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
                .where(
                    Payment.user_id == user.id,
                    Payment.provider == "yookassa",
                    Payment.status == "pending",
                    Payment.provider_payment_id.is_not(None),
                    Payment.created_at > dt.datetime.utcnow() - REUSE_MAX_AGE,
                    Payment.plan_id == plan.id,
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
    async with async_session() as session:
        payment = Payment(
            user_id=user.id, plan_id=plan.id, amount=plan.price,
            provider="yookassa", status="pending",
        )
        session.add(payment)
        await session.commit()
        local_id = payment.id

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
            await _abort_new(local_id)
        raise

    provider_id = data.get("id")
    url = (data.get("confirmation") or {}).get("confirmation_url")
    if not provider_id or not url:
        await _abort_new(local_id)
        raise YooKassaError("в ответе ЮKassa нет id платежа или confirmation_url")

    async with async_session() as session:
        payment = await session.get(Payment, local_id)
        payment.provider_payment_id = provider_id
        await session.commit()
    return url


async def _abort_new(payment_id: int) -> None:
    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        if payment is not None and payment.status == "pending" \
                and payment.provider_payment_id is None:
            payment.status = "canceled"
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
    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None or payment.status not in ("pending", "expired"):
            return
        user = await session.get(User, payment.user_id)
        payment.status = "canceled"
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
    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            return
        user_id = payment.user_id
    # Все операции одного пользователя (триал, оплата, понижение лимита) идут по очереди:
    # срок считается от актуального состояния клиента на Panel.
    async with user_lock(user_id):
        bonus_id = await _activate_in_lock(bot, payment_id)
    if bonus_id is not None:
        await apply_bonus(bot, bonus_id)


async def _activate_in_lock(bot: Bot, payment_id: int) -> int | None:
    sub_url = None
    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None or payment.status not in _CLAIMABLE:
            return
        previous_status = payment.status
        user = await session.get(User, payment.user_id)
        plan = await session.get(Plan, payment.plan_id) if payment.plan_id is not None else None
        if plan is None:
            payment.status = "paid_failed"
            await session.commit()
            logger.error("payment %s: у платежа нет тарифа (plan_id)", payment_id)
            if previous_status != "paid_failed":
                await _notify_admins(
                    bot,
                    f"⚠️ Платёж {payment_id} оплачен, но тариф не определён (plan_id пуст) — "
                    "требуется ручной разбор.",
                )
            return
        payment.status = "processing"
        await session.commit()

        panel = PanelApiClient()
        try:
            if payment.target_end_at is None:
                # Считается один раз и сохраняется ДО вызова Panel.
                payment.target_end_at = await compute_target_end(
                    panel, user.tg_id, plan.duration_days)
                await session.commit()
            target = payment.target_end_at
            result = await apply_period(
                panel, user=user, plan=plan, target_end_at=target, kind="paid")
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

        subscription = await save_subscription(session, user, plan, result, target, "paid")
        await session.flush()
        payment.subscription_id = subscription.id
        payment.status = "confirmed"
        has_receipt = (await session.execute(
            select(Receipt.id).where(Receipt.payment_id == payment.id)
        )).scalar_one_or_none()
        if has_receipt is None:
            session.add(Receipt(
                payment_id=payment.id, status="pending_review",
                amount=payment.amount, service_name=plan.name,
            ))
        bonus_id = await create_pending_bonus(session, user, plan, payment)
        await session.commit()
        user_tg_id, plan_name, amount_rub = user.tg_id, plan.name, payment.amount // 100
        sub_url = result.sub_url
        created = result.created
        downgrade_to, downgrade_base = result.downgrade_to, result.downgrade_base

    head = "Оплата получена, подписка активна" if created else "Оплата получена, подписка продлена"
    if sub_url:
        text = (f"{head} до {fmt_msk(target)} (МСК).\n\nСсылка на подписку:\n{sub_url}\n\n"
                "Откройте ссылку в браузере — на странице будет кнопка добавления "
                "профиля в приложение Happ (бесплатное: App Store, Google Play, happ.su).")
    else:
        text = (f"{head} до {fmt_msk(target)} (МСК), но ссылку сформировать "
                "автоматически не удалось. Обратитесь в поддержку.")
    if downgrade_to is not None and downgrade_base is not None:
        text += (f"\n\nЛимит устройств сохранится до {fmt_msk(downgrade_base)} (МСК), "
                 f"затем станет {downgrade_to}.")
    await _notify(bot, user_tg_id, text)
    await _notify_admins(
        bot,
        f"✅ Платёж {payment_id} подтверждён: «{plan_name}», {amount_rub} ₽. "
        + ("Чек: выпускается автоматически." if _receipts_enabled()
           else "Чек: черновик создан (pending_review), выпуск вручную."),
    )
    # Автовыдача чека (27.10.2026): сразу после активации платёжного алерта.
    # issue() сам пропустит вызов, если флаг NALOG_ISSUE_ENABLED выключен или чека нет.
    task = asyncio.create_task(_issue_receipt_task(bot, payment_id))
    _receipt_tasks.add(task)
    task.add_done_callback(_receipt_tasks.discard)
    return bonus_id


# Сильные ссылки на задачи автовыдачи: event loop держит задачи слабо, без ссылки
# задача может быть собрана GC во время сетевого ожидания.
_receipt_tasks: set[asyncio.Task] = set()


async def _issue_receipt_task(bot: Bot, payment_id: int) -> None:
    """Автовыдача чека по платежу (27.10.2026); issue() сам пропустит вызов,
    если NALOG_ISSUE_ENABLED выключен или чека у платежа нет. Ошибки изолированы."""
    try:
        async with async_session() as session:
            receipt_id = (await session.execute(
                select(Receipt.id).where(Receipt.payment_id == payment_id)
            )).scalar_one_or_none()
        if receipt_id is not None:
            await issue_receipt(bot, receipt_id)
    except Exception:
        logger.exception("автовыдача чека по платежу %s: сбой", payment_id)


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
                        payment.status = "expired"
                    continue
                if age > PENDING_EXPIRE_AFTER:
                    payment.status = "expired"
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


async def reconcile_loop(bot: Bot) -> None:
    while True:
        try:
            await reconcile_once(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("сверка платежей: сбой цикла")
        try:
            await apply_due_downgrades()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("отложенное понижение лимита устройств: сбой цикла")
        try:
            await retry_pending_bonuses(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("реферальные бонусы: сбой цикла")
        await asyncio.sleep(RECONCILE_INTERVAL_SEC)


def payments_enabled() -> bool:
    """Приём платежей включён, только когда заданы все настройки ЮKassa."""
    return all((YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY_FILE,
                YOOKASSA_WEBHOOK_SECRET, YOOKASSA_RETURN_URL))
