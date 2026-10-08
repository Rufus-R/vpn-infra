from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from app.db.base import async_session
from app.db.models import User
from app.keyboards import main_menu

router = Router()


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


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    # referrer_ref: deep-link параметр ref_<user_id> — записывается только для НОВОГО user
    # (bot.md, сценарий "реферальная ссылка": не перезаписывать для существующих)
    await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        referrer_ref=command.args,
    )
    await message.answer(
        "Добро пожаловать в «Штиль»! Выберите действие:",
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "menu:tariffs")
async def cb_tariffs(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("Раздел «Тарифы» в разработке — скоро здесь появится выбор.")


@router.callback_query(F.data == "menu:subs")
async def cb_subs(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("Раздел «Мои подписки» в разработке.")


@router.callback_query(F.data == "menu:ref")
async def cb_ref(callback: CallbackQuery) -> None:
    await callback.answer()
    me = await callback.bot.get_me()
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == callback.from_user.id))
        user = result.scalar_one_or_none()
    link = f"https://t.me/{me.username}?start=ref_{user.id}" if user else "ссылка недоступна"
    await callback.message.answer(f"Ваша реферальная ссылка:\n{link}")
