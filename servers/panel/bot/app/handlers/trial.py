"""Сценарий активации триала. См. docs/commercial/bot.md, 'Сценарий: активация триала'."""
import datetime as dt

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy import select

from app.config import REALITY_INBOUND_ID, SUB_BASE_URL
from app.db.base import async_session
from app.db.models import User, Plan, Subscription
from app.db.seed import TRIAL_PLAN_NAME
from app.panel_api import PanelApiClient, PanelApiError

router = Router()


class TrialStates(StatesGroup):
    waiting_contact = State()


@router.callback_query(F.data == "menu:trial")
async def cb_trial_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == callback.from_user.id))
        user = result.scalar_one_or_none()

    if user is None:
        await callback.message.answer("Сначала отправьте /start.")
        return

    if user.trial_used:
        await callback.message.answer("Пробный период уже был использован на этом аккаунте.")
        return

    if REALITY_INBOUND_ID is None:
        await callback.message.answer(
            "Пробный период временно недоступен (не настроен сервер). Попробуйте позже."
        )
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отправить номер телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await callback.message.answer(
        "Для защиты от повторных активаций нужен номер телефона. "
        "Нажмите кнопку ниже, чтобы отправить его.",
        reply_markup=keyboard,
    )
    await state.set_state(TrialStates.waiting_contact)


@router.message(TrialStates.waiting_contact, F.contact)
async def on_contact(message: Message, state: FSMContext) -> None:
    phone = message.contact.phone_number
    tg_id = message.from_user.id
    sub_url = None

    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("Сначала отправьте /start.", reply_markup=ReplyKeyboardRemove())
            await state.clear()
            return

        if user.trial_used:
            await message.answer("Пробный период уже использован.", reply_markup=ReplyKeyboardRemove())
            await state.clear()
            return

        conflict = await session.execute(
            select(User).where(User.phone_number == phone, User.id != user.id)
        )
        if conflict.scalar_one_or_none() is not None:
            await message.answer(
                "Этот номер телефона уже привязан к другому аккаунту — "
                "пробный период недоступен.",
                reply_markup=ReplyKeyboardRemove(),
            )
            await state.clear()
            return

        trial_plan_result = await session.execute(
            select(Plan).where(Plan.name == TRIAL_PLAN_NAME)
        )
        trial_plan = trial_plan_result.scalar_one_or_none()
        if trial_plan is None:
            await message.answer(
                "Пробный период временно недоступен (тариф не настроен). "
                "Сообщите администратору.",
                reply_markup=ReplyKeyboardRemove(),
            )
            await state.clear()
            return

        user.phone_number = phone

        now = dt.datetime.utcnow()
        end_at = now + dt.timedelta(days=trial_plan.duration_days)
        email = f"tg{tg_id}-trial@netru.bot"

        panel = PanelApiClient()
        try:
            await panel.add_client(
                email=email,
                limit_ip=trial_plan.device_count,
                total_gb=0,  # безлимит по трафику — ограничение по сроку/устройствам (допущение, см. чат)
                expiry_time_ms=int(end_at.timestamp() * 1000),
                inbound_ids=[REALITY_INBOUND_ID],
                tg_id=tg_id,
                comment=f"bot:trial:user{user.id}",
            )
            client_data = await panel.get_client(email)
            client = client_data["client"]
            sub_id = client.get("subId")
            # Ссылка подписки строится напрямую по шаблону Panel (SUB_BASE_URL + subId),
            # НЕ через subLinks/{subId} — этот эндпоинт отдаёт список сырых vless://
            # конфигов отдельных серверов, а не ссылку на страницу подписки
            # (подтверждено на практике 08.10.2026, см. чат/commit сессии).
            if sub_id and SUB_BASE_URL:
                sub_url = f"{SUB_BASE_URL}{sub_id}"
        except PanelApiError as exc:
            await message.answer(
                f"Не удалось создать пробную подписку (ошибка панели): {exc}\n"
                "Сообщите администратору.",
                reply_markup=ReplyKeyboardRemove(),
            )
            await state.clear()
            await panel.close()
            return
        finally:
            await panel.close()

        subscription = Subscription(
            user_id=user.id,
            panel_client_email=email,
            panel_client_uuid=client.get("uuid"),
            panel_client_sub_id=sub_id,
            inbound_ids=[REALITY_INBOUND_ID],
            plan_id=trial_plan.id,
            start_at=now,
            end_at=end_at,
            status="trial",
        )
        session.add(subscription)
        user.trial_used = True
        await session.commit()

    await state.clear()

    if sub_url:
        text = f"Пробная подписка создана на 7 дней!\n\nСсылка на подписку:\n{sub_url}"
    else:
        text = (
            "Пробная подписка создана на 7 дней, но не удалось сформировать ссылку "
            f"автоматически. Сообщите администратору, укажите ваш Telegram ID: {tg_id}"
        )
    await message.answer(text, reply_markup=ReplyKeyboardRemove())
