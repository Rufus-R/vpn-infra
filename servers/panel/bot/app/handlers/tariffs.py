"""Раздел «Тарифы».

🔴 11.10.2026 (решение оператора): приём платежей возможен ТОЛЬКО через ЮKassa
с автоматическим чеком. Ручной fallback (перевод + подтверждение админом без чека)
ПОЛНОСТЬЮ ОТКЛЮЧЁН как принцип, не как временная мера — процедура "выдавать чек
вручную через Мой налог для fallback-платежей" исключена оператором.

Кнопка «💳 Оформить заказ» в карточке тарифа ОСТАВЛЕНА в интерфейсе: нужна для
скриншотов в заявке на подключение приёма платежей в мессенджере (форма ЮKassa
требует показать "товары/услуги с ценами" и "кнопки оформления заказа" в уже
работающем, открытом для всех боте). При нажатии она больше НЕ создаёт
Payment/Subscription и не уведомляет админа — только сообщает пользователю,
что онлайн-оплата скоро заработает, и предлагает бесплатный триал.

Хендлеры admin:confirm:/admin:reject: НЕ удалены из файла — они написаны так,
что идентичны будущему обработчику вебхука ЮKassa (тот же блок add_client ->
get_client -> sub_url при переходе payment.status в confirmed), оставлены для
минимизации диффа при интеграции. Сейчас недостижимы: ни один Payment со
статусом pending через бота больше не создаётся.

См. docs/commercial/bot.md, раздел "Сценарий: покупка тарифа".
"""
import datetime as dt

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.config import ADMIN_IDS, REALITY_INBOUND_ID, SUB_BASE_URL
from app.db.base import async_session
from app.db.models import User, Plan, Subscription, Payment
from app.db.seed import TRIAL_PLAN_NAME
from app.handlers.start import require_consent, CONSENT_TEXT
from app.keyboards import tariffs_menu, plan_detail_keyboard, consent_keyboard
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
        "Онлайн-оплата через ЮKassa (с автоматическим чеком) подключается — "
        "совсем скоро можно будет оформить заказ прямо здесь."
    )
    await callback.message.answer(text, reply_markup=plan_detail_keyboard(plan.id), parse_mode="HTML")


@router.callback_query(F.data.startswith("plan:paid:"))
async def cb_plan_order(callback: CallbackQuery) -> None:
    """Кнопка «💳 Оформить заказ». 11.10.2026: приём платежей вне ЮKassa отключён —
    см. предупреждение в шапке файла. Эта функция больше не создаёт заявку на оплату."""
    await callback.answer()
    await callback.message.answer(
        "Онлайн-оплата временно недоступна — мы подключаем приём платежей через "
        "ЮKassa с автоматическим чеком. Совсем скоро можно будет оформить заказ "
        "прямо здесь.\n\n"
        "А пока доступен бесплатный пробный период — кнопка «🎁 Попробовать "
        "бесплатно» в главном меню."
    )


@router.callback_query(F.data.startswith("admin:confirm:"))
async def cb_admin_confirm(callback: CallbackQuery) -> None:
    # 11.10.2026: недостижимо из текущего кода бота (fallback отключён), оставлено
    # для переиспользования после интеграции вебхука ЮKassa — см. шапку файла.
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
    # 11.10.2026: недостижимо из текущего кода бота (fallback отключён), см. шапку файла.
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
