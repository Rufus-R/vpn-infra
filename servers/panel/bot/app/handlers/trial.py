"""Сценарий активации триала. См. docs/commercial/bot.md, 'Сценарий: активация триала'.

10.10.2026: запрос номера телефона убран (решение оператора) — антифрод держится
только на tg_id/trial_used (см. docs/commercial/overview.md, "Принятые риски").
Клиент создаётся сразу по нажатию "Попробовать бесплатно", без промежуточного шага.
"""
import datetime as dt

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.config import REALITY_INBOUND_ID, SUB_BASE_URL
from app.db.base import async_session
from app.db.models import User, Plan, Subscription
from app.db.seed import TRIAL_PLAN_NAME
from app.handlers.start import require_consent, CONSENT_TEXT
from app.keyboards import consent_keyboard
from app.panel_api import PanelApiClient, PanelApiError

router = Router()


@router.callback_query(F.data == "menu:trial")
async def cb_trial_start(callback: CallbackQuery) -> None:
    await callback.answer()
    gate_user = await require_consent(callback.from_user.id)
    if gate_user is None:
        await callback.message.answer(CONSENT_TEXT, reply_markup=consent_keyboard())
        return

    if gate_user.trial_used:
        await callback.message.answer("Пробный период уже был использован на этом аккаунте.")
        return

    if REALITY_INBOUND_ID is None:
        await callback.message.answer(
            "Пробный период временно недоступен (не настроен сервер). Попробуйте позже."
        )
        return

    sub_url = None
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == gate_user.id))
        user = result.scalar_one_or_none()
        if user.trial_used:
            await callback.message.answer("Пробный период уже использован.")
            return

        trial_plan_result = await session.execute(
            select(Plan).where(Plan.name == TRIAL_PLAN_NAME)
        )
        trial_plan = trial_plan_result.scalar_one_or_none()
        if trial_plan is None:
            await callback.message.answer(
                "Пробный период временно недоступен (тариф не настроен). "
                "Сообщите администратору."
            )
            return

        now = dt.datetime.utcnow()
        end_at = now + dt.timedelta(days=trial_plan.duration_days)
        email = f"tg{user.tg_id}-trial@netru.bot"

        panel = PanelApiClient()
        try:
            await panel.add_client(
                email=email,
                limit_ip=trial_plan.device_count,
                total_gb=0,  # безлимит по трафику — ограничение по сроку/устройствам
                expiry_time_ms=int(end_at.timestamp() * 1000),
                inbound_ids=[REALITY_INBOUND_ID],
                tg_id=user.tg_id,
                comment=f"bot:trial:user{user.id}",
            )
            client_data = await panel.get_client(email)
            client = client_data["client"]
            sub_id = client.get("subId")
            # Ссылка подписки строится напрямую по шаблону Panel (SUB_BASE_URL + subId),
            # НЕ через subLinks/{subId} — см. commercial/bot.md, "Интеграция с API Panel".
            if sub_id and SUB_BASE_URL:
                sub_url = f"{SUB_BASE_URL}{sub_id}"
        except PanelApiError as exc:
            await callback.message.answer(
                f"Не удалось создать пробную подписку (ошибка панели): {exc}\n"
                "Сообщите администратору."
            )
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

    if sub_url:
        text = f"Пробная подписка создана на 7 дней!\n\nСсылка на подписку:\n{sub_url}"
    else:
        text = (
            "Пробная подписка создана на 7 дней, но не удалось сформировать ссылку "
            f"автоматически. Сообщите администратору, укажите ваш Telegram ID: {gate_user.tg_id}"
        )
    await callback.message.answer(text)
