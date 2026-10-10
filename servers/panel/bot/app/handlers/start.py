"""Главное меню и согласие на обработку ПДн.

10.10.2026: добавлен обязательный экран согласия (ст. 9 152-ФЗ) — показывается
при первом /start, блокирует доступ к остальным разделам до нажатия кнопки
"Я согласен" (см. require_consent, используется также в trial.py и tariffs.py).
"""
import datetime as dt

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from app.db.base import async_session
from app.db.models import User
from app.keyboards import main_menu, consent_keyboard

router = Router()

CONSENT_TEXT = (
    "Добро пожаловать в «Штиль»!\n\n"
    "Прежде чем продолжить, ознакомьтесь с Политикой обработки персональных данных. "
    "Используя бота, вы подтверждаете согласие на обработку вашего Telegram ID и "
    "username в целях предоставления доступа к сервису."
)


async def get_or_create_user(tg_id: int, username: str | None,
                              referrer_ref: str | None = None) -> User:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar_one_or_none()
        if user is not None:
            return user

        referrer_id = None
        if referrer_ref and referrer_ref.startswith("ref_"):
            try:
                ref_user_id = int(referrer_ref.removeprefix("ref_"))
            except ValueError:
                ref_user_id = None
            if ref_user_id is not None:
                ref_result = await session.execute(select(User).where(User.id == ref_user_id))
                if ref_result.scalar_one_or_none() is not None:
                    referrer_id = ref_user_id

        user = User(tg_id=tg_id, username=username, referrer_id=referrer_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def require_consent(tg_id: int) -> User | None:
    """Возвращает User, если согласие на обработку ПДн уже дано; иначе None —
    вызывающий хендлер должен показать CONSENT_TEXT/consent_keyboard() и
    прекратить дальнейшую обработку (не создавать подписки/заявки на оплату)."""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar_one_or_none()
    if user is None or not user.privacy_accepted:
        return None
    return user


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    # referrer_ref: deep-link параметр ref_<user_id> — записывается только для НОВОГО user
    # (bot.md, сценарий "реферальная ссылка": не перезаписывать для существующих)
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        referrer_ref=command.args,
    )
    if not user.privacy_accepted:
        await message.answer(CONSENT_TEXT, reply_markup=consent_keyboard())
        return
    await message.answer("С возвращением! Выберите действие:", reply_markup=main_menu())


@router.callback_query(F.data == "consent:accept")
async def cb_consent_accept(callback: CallbackQuery) -> None:
    await callback.answer()
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.message.answer("Сначала отправьте /start.")
            return
        user.privacy_accepted = True
        user.privacy_accepted_at = dt.datetime.utcnow()
        await session.commit()
    await callback.message.answer("Спасибо! Выберите действие:", reply_markup=main_menu())


@router.callback_query(F.data == "menu:back")
async def cb_back(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await require_consent(callback.from_user.id)
    if user is None:
        await callback.message.answer(CONSENT_TEXT, reply_markup=consent_keyboard())
        return
    await callback.message.answer("Выберите действие:", reply_markup=main_menu())


@router.callback_query(F.data == "menu:subs")
async def cb_subs(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await require_consent(callback.from_user.id)
    if user is None:
        await callback.message.answer(CONSENT_TEXT, reply_markup=consent_keyboard())
        return
    await callback.message.answer("Раздел «Мои подписки» в разработке.")


@router.callback_query(F.data == "menu:ref")
async def cb_ref(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await require_consent(callback.from_user.id)
    if user is None:
        await callback.message.answer(CONSENT_TEXT, reply_markup=consent_keyboard())
        return
    me = await callback.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{user.id}"
    await callback.message.answer(f"Ваша реферальная ссылка:\n{link}")
