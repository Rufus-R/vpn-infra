"""Раздел «Тарифы».

Кнопка «💳 Оформить заказ» создаёт платёж ЮKassa (app/payments.py, start_payment) и
показывает кнопку со ссылкой на оплату; подписку выдаёт обработка вебхука/сверки
(app/payments.py), а не этот файл. Пока настройки ЮKassa не заданы (payments_enabled()
== False), кнопка показывает прежнее сообщение «оплата скоро».

Хендлеры admin:confirm:/admin:reject: (остатки отключённой 11.10.2026 fallback-оплаты)
удалены 19.10.2026; активацию подписки выполняет app/payments.py.

См. docs/commercial/bot.md, раздел "Сценарий: покупка тарифа".
"""
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.db.base import async_session
from app.db.models import Plan
from app.db.seed import TRIAL_PLAN_NAME
from app.handlers.start import require_consent, CONSENT_TEXT
from app.keyboards import tariffs_menu, plan_detail_keyboard, consent_keyboard, pay_keyboard
from app.payments import ActiveSubscriptionError, payments_enabled, start_payment
from app.yookassa_api import YooKassaError

router = Router()
logger = logging.getLogger("tariffs")


def _payment_note() -> str:
    if payments_enabled():
        return "Оплата через ЮKassa. После оплаты подписка активируется автоматически."
    return (
        "Онлайн-оплата через ЮKassa (с автоматическим чеком) подключается — "
        "совсем скоро можно будет оформить заказ прямо здесь."
    )


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
        + _payment_note()
    )
    await callback.message.answer(text, reply_markup=plan_detail_keyboard(plan.id), parse_mode="HTML")


@router.callback_query(F.data.startswith("plan:paid:"))
async def cb_plan_order(callback: CallbackQuery) -> None:
    """Кнопка «💳 Оформить заказ»: создаёт платёж ЮKassa и отдаёт ссылку на оплату.
    Пока ЮKassa не настроена — прежнее сообщение «оплата скоро»."""
    await callback.answer()
    if not payments_enabled():
        await callback.message.answer(
            "Онлайн-оплата временно недоступна — мы подключаем приём платежей через "
            "ЮKassa с автоматическим чеком. Совсем скоро можно будет оформить заказ "
            "прямо здесь.\n\n"
            "А пока доступен бесплатный пробный период — кнопка «🎁 Попробовать "
            "бесплатно» в главном меню."
        )
        return
    user = await require_consent(callback.from_user.id)
    if user is None:
        await callback.message.answer(CONSENT_TEXT, reply_markup=consent_keyboard())
        return
    plan_id = int(callback.data.removeprefix("plan:paid:"))
    try:
        url = await start_payment(user.tg_id, plan_id)
    except ActiveSubscriptionError as exc:
        await callback.message.answer(
            f"У вас уже есть действующая платная подписка (до {exc.active_until:%d.%m.%Y}). "
            "Новый заказ пока оформить нельзя — продление появится позже. "
            "Ссылку на подписку можно открыть в разделе «📱 Мои подписки»."
        )
        return
    except (YooKassaError, ValueError):
        logger.exception("не удалось создать платёж: tg_id=%s plan_id=%s", user.tg_id, plan_id)
        await callback.message.answer(
            "Не удалось создать платёж. Попробуйте чуть позже или обратитесь в «Поддержку»."
        )
        return
    await callback.message.answer(
        "Заказ создан. Нажмите кнопку ниже, чтобы перейти к оплате. После оплаты "
        "подписка придёт сюда автоматически.",
        reply_markup=pay_keyboard(url),
    )
