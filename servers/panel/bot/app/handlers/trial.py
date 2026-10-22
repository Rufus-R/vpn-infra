"""Сценарий активации триала. См. docs/commercial/bot.md, 'Сценарий: активация триала'.

10.10.2026: запрос номера телефона убран (решение оператора) — антифрод держится
только на tg_id/trial_used (см. docs/commercial/overview.md, "Принятые риски").
22.10.2026: один клиент на пользователя — триал создаёт клиента `tg{tg_id}@netru.bot` или,
если он уже есть (например, после покупки), добавляет к его сроку дни триала; ссылка подписки
не меняется. Логика — app/subscription_service.py.
"""
import logging

import httpx
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.config import REALITY_INBOUND_ID
from app.db.base import async_session
from app.db.models import User, Plan
from app.db.seed import TRIAL_PLAN_NAME
from app.handlers.start import require_consent, CONSENT_TEXT
from app.keyboards import consent_keyboard
from app.panel_api import PanelApiClient, PanelApiError
from app.timeutil import fmt_msk
from app.subscription_service import (
    apply_period, compute_target_end, save_subscription, user_lock,
)

router = Router()
logger = logging.getLogger("trial")


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
    target = None
    # Блокировка пользователя + повторная проверка trial_used внутри неё: два быстрых
    # нажатия кнопки не дадут два триала.
    async with user_lock(gate_user.id):
        async with async_session() as session:
            user = (await session.execute(
                select(User).where(User.id == gate_user.id)
            )).scalar_one()
            if user.trial_used:
                await callback.message.answer("Пробный период уже использован.")
                return

            trial_plan = (await session.execute(
                select(Plan).where(Plan.name == TRIAL_PLAN_NAME)
            )).scalar_one_or_none()
            if trial_plan is None:
                await callback.message.answer(
                    "Пробный период временно недоступен (тариф не настроен). "
                    "Сообщите администратору."
                )
                return

            panel = PanelApiClient()
            try:
                target = await compute_target_end(
                    panel, user.tg_id, trial_plan.duration_days)
                result = await apply_period(
                    panel, user=user, plan=trial_plan, target_end_at=target, kind="trial")
            except (PanelApiError, httpx.HTTPError):
                logger.exception("триал: сбой Panel, user_id=%s", user.id)
                await callback.message.answer(
                    "Не удалось создать пробную подписку (ошибка панели). "
                    "Попробуйте позже или обратитесь в «Поддержку»."
                )
                return
            finally:
                await panel.close()

            await save_subscription(session, user, trial_plan, result, target, "trial")
            user.trial_used = True
            await session.commit()
            sub_url = result.sub_url
            tg_id = user.tg_id

    if sub_url:
        text = (f"Пробный период активирован, действует до {fmt_msk(target)} (МСК).\n\n"
                f"Ссылка на подписку:\n{sub_url}")
    else:
        text = (
            "Пробный период активирован, но не удалось сформировать ссылку "
            f"автоматически. Сообщите администратору, укажите ваш Telegram ID: {tg_id}"
        )
    await callback.message.answer(text)
