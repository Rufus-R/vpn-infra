"""Раздел «Рассылка» админ-меню (24.10.2026): только сервисные сообщения.

Сценарий: adm:bc:menu -> выбор аудитории -> текст одним сообщением -> предпросмотр ->
(пробная отправка себе) -> подтверждение. Черновик хранится в БД (broadcasts, draft); FSM
держит только ожидание текста (MemoryStorage не переживает рестарт). Отправка и журнал
доставок — app/broadcast.py. Доступ — только ADMIN_IDS (фильтры на callback_query и message).
В списках — внутренние user_id, без username.
"""
from __future__ import annotations

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.broadcast import (
    AUDIENCES, audience_user_ids, cancel_draft, create_draft, get_broadcast,
    set_draft_body, start_broadcast, start_send,
)
from app.config import ADMIN_IDS
from app.db.base import async_session
from app.handlers.admin import _show
from app.keyboards import admin_back_keyboard

router = Router()
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))
router.message.filter(F.from_user.id.in_(ADMIN_IDS))

MAX_TEXT_LEN = 3500
PREVIEW_IDS_LIMIT = 30

_MENU_TEXT = (
    "📣 Рассылка\n\n"
    "Только сервисные сообщения (пробный период, срок подписки, изменения условий). "
    "Исключены: без согласия на ПДн, привязанные ручные клиенты, администраторы.\n\n"
    "Выберите аудиторию:"
)
_PROMPT_TEXT = (
    "Аудитория: {label}\n\n"
    "Пришлите текст одним сообщением (обычный текст, до {limit} символов, "
    "не начиная с «/»)."
)


class BroadcastStates(StatesGroup):
    waiting_text = State()


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _bc_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("⬅️ Рассылка", "adm:bc:menu")]])


async def _show_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        counts = {key: len(await audience_user_ids(session, key)) for key in AUDIENCES}
    rows = [
        [_btn(f"{label} ({counts[key]})", f"adm:bc:aud:{key}")]
        for key, label in AUDIENCES.items()
    ]
    rows.append([_btn("⬅️ Админ-меню", "adm:menu")])
    await _show(callback, _MENU_TEXT, InlineKeyboardMarkup(inline_keyboard=rows))


async def _preview(broadcast_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    info = await get_broadcast(broadcast_id)
    if info is None or info.status != "draft":
        return None
    async with async_session() as session:
        ids = await audience_user_ids(session, info.audience)
    if ids:
        shown = ", ".join(str(i) for i in ids[:PREVIEW_IDS_LIMIT])
        if len(ids) > PREVIEW_IDS_LIMIT:
            shown += ", …"
        recipients = f"Получателей: {len(ids)} (user_id: {shown})"
    else:
        recipients = "Получателей нет."
    text = (
        f"📣 Предпросмотр рассылки #{broadcast_id}\n"
        f"Аудитория: {AUDIENCES.get(info.audience, info.audience)}\n"
        f"{recipients}\n\n"
        f"— текст —\n{info.body}\n— конец —"
    )
    rows = [[_btn("🧪 Пробная отправка мне", f"adm:bc:test:{broadcast_id}")]]
    if ids:
        rows.append([_btn(f"✅ Отправить ({len(ids)})", f"adm:bc:go:{broadcast_id}")])
    rows.append([_btn("✏️ Изменить текст", f"adm:bc:edit:{broadcast_id}")])
    rows.append([_btn("❌ Отмена", f"adm:bc:cancel:{broadcast_id}")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:bc:menu")
async def cb_bc_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _show_menu(callback, state)


@router.callback_query(F.data.startswith("adm:bc:aud:"))
async def cb_bc_audience(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    key = callback.data.split(":")[3]
    if key not in AUDIENCES:
        return
    await state.set_state(BroadcastStates.waiting_text)
    await state.update_data(audience=key, draft_id=None)
    await _show(
        callback,
        _PROMPT_TEXT.format(label=AUDIENCES[key], limit=MAX_TEXT_LEN),
        _bc_back_keyboard(),
    )


@router.callback_query(F.data.startswith("adm:bc:edit:"))
async def cb_bc_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    draft_id = int(callback.data.split(":")[3])
    info = await get_broadcast(draft_id)
    if info is None or info.status != "draft":
        await _show_menu(callback, state)
        return
    await state.set_state(BroadcastStates.waiting_text)
    await state.update_data(audience=info.audience, draft_id=draft_id)
    await _show(
        callback,
        _PROMPT_TEXT.format(label=AUDIENCES.get(info.audience, info.audience), limit=MAX_TEXT_LEN),
        _bc_back_keyboard(),
    )


@router.message(BroadcastStates.waiting_text, F.text)
async def msg_bc_text(message: Message, state: FSMContext) -> None:
    text = message.text
    if text.startswith("/"):
        await message.answer("Текст не должен начинаться с «/». Пришлите текст ещё раз.")
        return
    if len(text) > MAX_TEXT_LEN:
        await message.answer(
            f"Слишком длинно: {len(text)} символов, максимум {MAX_TEXT_LEN}. "
            "Пришлите текст ещё раз.")
        return
    data = await state.get_data()
    audience = data.get("audience")
    draft_id = data.get("draft_id")
    if audience not in AUDIENCES:
        await state.clear()
        await message.answer("Сценарий сброшен. Откройте раздел «Рассылка» заново.")
        return
    if draft_id is None:
        draft_id = await create_draft(message.from_user.id, audience, text)
    elif not await set_draft_body(draft_id, text):
        await state.clear()
        await message.answer("Рассылка уже запущена или отменена — изменить текст нельзя.")
        return
    await state.clear()
    preview = await _preview(draft_id)
    if preview is None:
        await message.answer("Черновик не найден.")
        return
    await message.answer(preview[0], reply_markup=preview[1])


@router.callback_query(F.data.startswith("adm:bc:test:"))
async def cb_bc_test(callback: CallbackQuery) -> None:
    info = await get_broadcast(int(callback.data.split(":")[3]))
    if info is None:
        await callback.answer("Черновик не найден", show_alert=True)
        return
    try:
        await callback.bot.send_message(callback.from_user.id, info.body)
    except Exception as exc:
        await callback.answer(f"Не удалось отправить: {type(exc).__name__}", show_alert=True)
        return
    await callback.answer("Пробное сообщение отправлено вам")


@router.callback_query(F.data.startswith("adm:bc:go:"))
async def cb_bc_go(callback: CallbackQuery) -> None:
    await callback.answer()
    broadcast_id = int(callback.data.split(":")[3])
    count = await start_broadcast(broadcast_id)
    if count is None:
        await _show(callback, "Рассылка уже запущена или отменена.", admin_back_keyboard())
        return
    if count == 0:
        await _show(callback, "Получателей нет, рассылка не запущена.", admin_back_keyboard())
        return
    start_send(callback.bot, broadcast_id)
    await _show(
        callback,
        f"📣 Рассылка #{broadcast_id} запущена: {count} получателей. "
        "Отчёт придёт в этот чат по окончании.",
        admin_back_keyboard(),
    )


@router.callback_query(F.data.startswith("adm:bc:cancel:"))
async def cb_bc_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await cancel_draft(int(callback.data.split(":")[3]))
    await _show_menu(callback, state)
