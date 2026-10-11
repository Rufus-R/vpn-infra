"""Раздел «Поддержка».

Обязательство из юридических документов (Политика п.6, Оферта пп.6.2/9.2) —
обращения пользователей принимаются через раздел «Поддержка» бота.

Схема:
1. Пользователь жмёт «📞 Поддержка» → FSM-состояние waiting_message.
2. Следующее текстовое сообщение пересылается КАЖДОМУ ADMIN_IDS отдельной копией.
   Все копии одного обращения сгруппированы полем source_message_id (message_id
   ОРИГИНАЛЬНОГО сообщения пользователя) — используется для cross-admin
   уведомления "уже отвечено" (см. ниже).
3. Любой администратор отвечает Reply на пересланную копию → бот находит
   SupportMessage по (admin_tg_id, admin_message_id) → пересылает ответ
   пользователю → помечает ВЕСЬ тред (user_id, source_message_id) answered=True
   → редактирует копии у ОСТАЛЬНЫХ админов, дописывая "✅ Отвечено другим
   администратором", чтобы снизить риск дублирующего ответа (не устраняет
   полностью гонку при одновременном ответе двух админов за доли секунды).
4. /queue (только для ADMIN_IDS, для прочих — молча игнорируется, как и любая
   нераспознанная команда в текущем коде) — список необработанных обращений,
   адресованных ИМЕННО этому админу (answered=False), каждое отдельным
   сообщением с рабочим Reply (чтобы на карточку из очереди можно было ответить).

Ограничение MVP: FSM-состояние в MemoryStorage (дефолт Dispatcher() в main.py,
не настраивался явно) — не переживает рестарт бота.
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.config import ADMIN_IDS
from app.db.base import async_session
from app.db.models import SupportMessage, User
from app.handlers.start import require_consent, CONSENT_TEXT
from app.keyboards import consent_keyboard

router = Router()


class SupportStates(StatesGroup):
    waiting_message = State()


@router.callback_query(F.data == "menu:support")
async def cb_support_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    user = await require_consent(callback.from_user.id)
    if user is None:
        await callback.message.answer(CONSENT_TEXT, reply_markup=consent_keyboard())
        return
    await state.set_state(SupportStates.waiting_message)
    await callback.message.answer(
        "Опишите вашу проблему или вопрос одним сообщением — мы ответим в этом чате."
    )


@router.message(SupportStates.waiting_message, F.text)
async def msg_support_text(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("Сначала отправьте /start.")
            return

        if not ADMIN_IDS:
            await message.answer(
                "Не удалось передать сообщение — поддержка временно недоступна. "
                "Попробуйте позже."
            )
            return

        username = f"@{message.from_user.username}" if message.from_user.username else "—"
        forward_text = (
            f"📩 Новое обращение в поддержку\n"
            f"От: tg_id={user.tg_id}, username={username}, user_id={user.id}\n\n"
            f"{message.text}"
        )

        delivered = False
        for admin_id in ADMIN_IDS:
            try:
                sent = await message.bot.send_message(admin_id, forward_text)
            except Exception:
                continue
            delivered = True
            session.add(SupportMessage(
                user_id=user.id,
                direction="user",
                body=message.text,
                source_message_id=message.message_id,
                admin_tg_id=admin_id,
                admin_message_id=sent.message_id,
            ))
        await session.commit()

    if delivered:
        await message.answer("Сообщение передано. Мы ответим вам в этом чате.")
    else:
        await message.answer(
            "Не удалось передать сообщение администратору. Попробуйте позже."
        )


async def _mark_thread_answered_and_notify(session, bot, original: SupportMessage,
                                            replying_admin_id: int) -> None:
    """Помечает ВСЕ строки треда (user_id, source_message_id) answered=True и
    редактирует копии у ОСТАЛЬНЫХ админов (кроме ответившего) с пометкой."""
    result = await session.execute(
        select(SupportMessage).where(
            SupportMessage.user_id == original.user_id,
            SupportMessage.source_message_id == original.source_message_id,
            SupportMessage.direction == "user",
            SupportMessage.answered == False,  # noqa: E712
        )
    )
    siblings = result.scalars().all()
    for row in siblings:
        row.answered = True
        if row.admin_tg_id != replying_admin_id and row.admin_message_id is not None:
            try:
                await bot.edit_message_text(
                    chat_id=row.admin_tg_id,
                    message_id=row.admin_message_id,
                    text=f"✅ Отвечено другим администратором",
                )
            except Exception:
                pass  # сообщение могло быть уже удалено/отредактировано — не критично


@router.message(F.from_user.id.in_(ADMIN_IDS), F.reply_to_message, F.text)
async def msg_admin_reply(message: Message) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(SupportMessage).where(
                SupportMessage.admin_tg_id == message.from_user.id,
                SupportMessage.admin_message_id == message.reply_to_message.message_id,
                SupportMessage.direction == "user",
            )
        )
        original = result.scalar_one_or_none()
        if original is None:
            return  # Reply не на сообщение поддержки — пропускаем

        if original.answered:
            await message.reply("Уже отвечено другим администратором.")
            return

        user = await session.get(User, original.user_id)
        if user is None:
            await message.reply("Не удалось найти пользователя (возможно, удалён).")
            return

        session.add(SupportMessage(
            user_id=user.id,
            direction="admin",
            body=message.text,
        ))
        await _mark_thread_answered_and_notify(session, message.bot, original, message.from_user.id)
        await session.commit()

    try:
        await message.bot.send_message(
            user.tg_id,
            f"📬 Ответ поддержки:\n\n{message.text}",
        )
    except Exception:
        await message.reply("Не удалось доставить ответ пользователю (бот заблокирован?).")
        return

    await message.reply("✅ Отправлено пользователю.")


@router.message(Command("queue"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_support_queue(message: Message) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(SupportMessage).where(
                SupportMessage.admin_tg_id == message.from_user.id,
                SupportMessage.direction == "user",
                SupportMessage.answered == False,  # noqa: E712
            ).order_by(SupportMessage.created_at)
        )
        pending = result.scalars().all()

    if not pending:
        await message.answer("Очередь пуста — нет необработанных обращений.")
        return

    for item in pending:
        async with async_session() as session:
            user = await session.get(User, item.user_id)
        username = f"@{user.username}" if user and user.username else "—"
        text = (
            f"📩 Обращение от tg_id={user.tg_id if user else '?'}, "
            f"username={username}\n\n{item.body}"
        )
        sent = await message.answer(text)
        # Обновить admin_message_id на карточку из очереди — чтобы Reply сработал
        async with async_session() as session:
            row = await session.get(SupportMessage, item.id)
            row.admin_message_id = sent.message_id
            await session.commit()
