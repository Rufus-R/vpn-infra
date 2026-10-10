"""Раздел «Тарифы» + fallback-оплата (ручное подтверждение админом).
См. docs/commercial/bot.md, 'Сценарий: покупка тарифа' (fallback-путь).

MVP 09.10.2026: только fallback, ЮKassa не подключена (регистрация завершена,
интеграция — следующий этап). Реквизиты — PAYMENT_REQUISITES_TEXT (.env, не хардкод).

Subscription.status временно используется как свободная строка для состояния заявки
(pending_payment/rejected/active) — без схемных изменений, т.к. это MVP до появления
полноценной модели заказов.
"""
import datetime as dt

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.config import ADMIN_IDS, PAYMENT_REQUISITES_TEXT, REALITY_INBOUND_ID, SUB_BASE_URL
from app.db.base import async_session
from app.db.models import User, Plan, Subscription, Payment
from app.db.seed import TRIAL_PLAN_NAME
from app.handlers.start import require_consent, CONSENT_TEXT
from app.keyboards import (
    tariffs_menu, plan_detail_keyboard, admin_payment_keyboard, consent_keyboard,
)
from app.panel_api import PanelApiClient, PanelApiError

router = Router()


@router.callback_query(F.data == "menu:tariffs")
async def cb_tariffs(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await require_consent(callback.from_user.id)
    if user is None:
        await callback.message.answer(CONSENT_TEXT, reply_markup=consent_keyboard())
        return
    async with async_session() as session:
        result = await session.execute(
            select(Plan)
            .where(Plan.name != TRIAL_PLAN_NAME)
            .order_by(Plan.device_count, Plan.duration_days)
        )
        plans = result.scalars().all()
    if not plans:
        await callback.message.answer("Тарифы временно недоступны.")
        return
    await callback.message.answer("Выберите тариф:", reply_markup=tariffs_menu(plans))


@router.callback_query(F.data.startswith("plan:detail:"))
async def cb_plan_detail(callback: CallbackQuery) -> None:
    await callback.answer()
    plan_id = int(callback.data.removeprefix("plan:detail:"))
    async with async_session() as session:
        plan = await session.get(Plan, plan_id)
    if plan is None:
        await callback.message.answer("Тариф не найден.")
        return
    price_rub = plan.price // 100
    text = (
        f"<b>{plan.name}</b>\n\n"
        f"{plan.description or ''}\n\n"
        f"Стоимость: {price_rub} ₽ / {plan.duration_days} дн.\n"
        f"Устройств: {plan.device_count}\n\n"
        f"{PAYMENT_REQUISITES_TEXT}\n\n"
        "После перевода нажмите «✅ Я оплатил» — заявка уйдёт администратору "
        "на подтверждение."
    )
    await callback.message.answer(text, reply_markup=plan_detail_keyboard(plan.id), parse_mode="HTML")


@router.callback_query(F.data.startswith("plan:paid:"))
async def cb_plan_paid(callback: CallbackQuery) -> None:
    """Пользователь нажал «Я оплатил» — создаём pending-заявку, уведомляем админов.
    Реальное списание/проверка платежа не производится (fallback, ручное подтверждение)."""
    await callback.answer()
    plan_id = int(callback.data.removeprefix("plan:paid:"))
    tg_id = callback.from_user.id

    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.message.answer("Сначала отправьте /start.")
            return

        plan = await session.get(Plan, plan_id)
        if plan is None:
            await callback.message.answer("Тариф не найден.")
            return

        now = dt.datetime.utcnow()
        placeholder_email = f"pending-tg{tg_id}-{int(now.timestamp() * 1000)}@netru.bot"

        subscription = Subscription(
            user_id=user.id,
            panel_client_email=placeholder_email,
            panel_client_uuid=None,
            panel_client_sub_id=None,
            inbound_ids=[],
            plan_id=plan.id,
            start_at=now,
            end_at=now,
            status="pending_payment",
        )
        session.add(subscription)
        await session.flush()  # получить subscription.id до commit

        payment = Payment(
            user_id=user.id,
            subscription_id=subscription.id,
            amount=plan.price,
            provider="manual",
            status="pending",
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)

        payment_id = payment.id
        plan_name = plan.name
        plan_price = plan.price

    await callback.message.answer(
        "Заявка на оплату отправлена администратору. Как только оплата будет "
        "подтверждена, вы получите ссылку на подписку."
    )

    admin_text = (
        f"🆕 Заявка на оплату (fallback)\n"
        f"Пользователь: tg_id={tg_id} (@{callback.from_user.username or '-'})\n"
        f"Тариф: {plan_name}\n"
        f"Сумма: {plan_price // 100} ₽\n"
        f"Payment ID: {payment_id}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await callback.bot.send_message(
                admin_id, admin_text, reply_markup=admin_payment_keyboard(payment_id)
            )
        except Exception:
            # Не роняем обработчик, если конкретный админ недоступен/заблокировал бота
            pass


@router.callback_query(F.data.startswith("admin:confirm:"))
async def cb_admin_confirm(callback: CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return
    await callback.answer()
    payment_id = int(callback.data.removeprefix("admin:confirm:"))

    sub_url = None
    error_text = None
    user_tg_id = None

    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None or payment.status != "pending":
            await callback.message.answer("Заявка не найдена или уже обработана.")
            return

        subscription = await session.get(Subscription, payment.subscription_id)
        plan = await session.get(Plan, subscription.plan_id)
        user = await session.get(User, payment.user_id)
        user_tg_id = user.tg_id

        now = dt.datetime.utcnow()
        end_at = now + dt.timedelta(days=plan.duration_days)
        email = f"tg{user.tg_id}-sub{subscription.id}@netru.bot"

        panel = PanelApiClient()
        try:
            await panel.add_client(
                email=email,
                limit_ip=plan.device_count,
                total_gb=0,
                expiry_time_ms=int(end_at.timestamp() * 1000),
                inbound_ids=[REALITY_INBOUND_ID],
                tg_id=user.tg_id,
                comment=f"bot:paid:sub{subscription.id}",
            )
            client_data = await panel.get_client(email)
            client = client_data["client"]
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
            await session.commit()
        except PanelApiError as exc:
            error_text = str(exc)
        finally:
            await panel.close()

    if error_text:
        await callback.message.answer(
            f"Ошибка при создании клиента на панели: {error_text}\n"
            f"Payment ID {payment_id} остаётся в статусе pending, повторите вручную."
        )
        return

    await callback.message.edit_text(callback.message.text + "\n\n✅ ПОДТВЕРЖДЕНО")

    if sub_url:
        text = f"Оплата подтверждена! Ваша подписка активна.\n\nСсылка на подписку:\n{sub_url}"
    else:
        text = (
            "Оплата подтверждена, подписка создана, но не удалось сформировать ссылку "
            "автоматически. Обратитесь в поддержку."
        )
    try:
        await callback.bot.send_message(user_tg_id, text)
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin:reject:"))
async def cb_admin_reject(callback: CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return
    await callback.answer()
    payment_id = int(callback.data.removeprefix("admin:reject:"))

    user_tg_id = None
    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None or payment.status != "pending":
            await callback.message.answer("Заявка не найдена или уже обработана.")
            return
        subscription = await session.get(Subscription, payment.subscription_id)
        user = await session.get(User, payment.user_id)
        user_tg_id = user.tg_id

        payment.status = "rejected"
        subscription.status = "rejected"
        await session.commit()

    await callback.message.edit_text(callback.message.text + "\n\n❌ ОТКЛОНЕНО")
    try:
        await callback.bot.send_message(
            user_tg_id,
            "Ваша заявка на оплату отклонена. Если это ошибка — обратитесь в поддержку.",
        )
    except Exception:
        pass
