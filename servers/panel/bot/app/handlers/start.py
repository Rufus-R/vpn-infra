"""Главное меню и согласие на обработку ПДн.

10.10.2026: добавлен обязательный экран согласия (ст. 9 152-ФЗ) — показывается
при первом /start, блокирует доступ к остальным разделам до нажатия кнопки
"Я согласен" (см. require_consent, используется также в trial.py и tariffs.py).
"""
import datetime as dt

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select

from app.db.base import async_session
from app.db.models import Subscription, User
from app.config import ADMIN_IDS
from app.keyboards import main_menu, consent_keyboard

router = Router()

CONSENT_TEXT = (
    "Добро пожаловать в «Штиль»!\n\n"
    "Для работы с ботом нужны два отдельных действия:\n"
    "1. Акцепт публичной оферты — условия оказания услуг; текст доступен по кнопке «📄 Публичная оферта» до подтверждения.\n"
    "2. Согласие на обработку персональных данных (152-ФЗ) — кнопка «🔒 Согласен на обработку ПДн».\n\n"
    "Обрабатываются: Telegram ID и username — для авторизации и предоставления доступа; "
    "IP подключённых устройств — для контроля лимита подключений, хранится не дольше 1 часа после последнего использования. Согласие можно отозвать в разделе «📚 Документы и согласие»."
)


async def _has_active_subscription(user_id: int) -> bool:
    async with async_session() as session:
        count = (await session.execute(
            select(func.count()).select_from(Subscription)
            .where(Subscription.user_id == user_id)
            .where(Subscription.status.in_(("active", "trial", "family")))
            .where(Subscription.end_at > dt.datetime.utcnow())
        )).scalar_one()
    return count > 0

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
    await message.answer("С возвращением! Выберите действие:",
                         reply_markup=main_menu(
                             is_admin=message.from_user.id in ADMIN_IDS,
                             trial_used=user.trial_used,
                             has_subscription=await _has_active_subscription(user.id)))


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
    await callback.message.answer("Спасибо! Выберите действие:",
                                  reply_markup=main_menu(
                                      is_admin=callback.from_user.id in ADMIN_IDS,
                                      trial_used=user.trial_used,
                                      has_subscription=await _has_active_subscription(user.id)))


@router.callback_query(F.data == "menu:back")
async def cb_back(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await require_consent(callback.from_user.id)
    if user is None:
        await callback.message.answer(CONSENT_TEXT, reply_markup=consent_keyboard())
        return
    await callback.message.answer("Выберите действие:",
                                  reply_markup=main_menu(
                                      is_admin=callback.from_user.id in ADMIN_IDS,
                                      trial_used=user.trial_used,
                                      has_subscription=await _has_active_subscription(user.id)))


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


def _docs_keyboard(with_revoke: bool = True) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📄 Публичная оферта", url="https://netru.ru.net/oferta")],
        [InlineKeyboardButton(text="🔒 Политика обработки ПДн", url="https://netru.ru.net/privacy")],
    ]
    if with_revoke:
        rows.append([InlineKeyboardButton(
            text="🚫 Отозвать согласие на обработку ПДн", callback_data="consent:revoke")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "menu:docs")
async def cb_docs(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await require_consent(callback.from_user.id)
    if user is None:
        await callback.message.answer(CONSENT_TEXT, reply_markup=consent_keyboard())
        return
    await callback.message.answer(
        "Документы сервиса:\n\n"
        "📄 Оферта — условия оказания услуг.\n"
        "🔒 Политика — как обрабатываются ваши данные (152-ФЗ).\n\n"
        "Согласие на обработку ПДн можно отозвать кнопкой ниже. После отзыва функции бота "
        "станут недоступны; сведения, которые мы обязаны хранить по закону (о платежах и "
        "чеках), сохраняются.",
        reply_markup=_docs_keyboard(),
    )


@router.callback_query(F.data == "consent:revoke")
async def cb_revoke(callback: CallbackQuery) -> None:
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, отозвать согласие", callback_data="consent:revoke:confirm")],
        [InlineKeyboardButton(text="Отмена", callback_data="consent:revoke:cancel")],
    ])
    await callback.message.answer(
        "Отозвать согласие на обработку персональных данных?\n\n"
        "Функции бота станут недоступны. Отменить отзыв кнопкой нельзя — "
        "восстановление через /start или «Поддержку».",
        reply_markup=kb,
    )


@router.callback_query(F.data == "consent:revoke:cancel")
async def cb_revoke_cancel(callback: CallbackQuery) -> None:
    await callback.answer("Отменено")
    await callback.message.answer("Действие отменено. Данные обрабатываются как прежде.")


@router.callback_query(F.data == "consent:revoke:confirm")
async def cb_revoke_confirm(callback: CallbackQuery) -> None:
    await callback.answer()
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.message.answer("Сначала отправьте /start.")
            return
        user.privacy_accepted = False
        user.privacy_accepted_at = None
        await session.commit()
    await callback.message.answer(
        "Согласие на обработку персональных данных отозвано. Функции бота недоступны.\n\n"
        "Отправьте /start, чтобы заново ознакомиться с документами и дать согласие."
    )
