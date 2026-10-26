"""Экраны выпуска чеков в админ-меню (патч №3, 26.10.2026).

Список остаётся на прежнем callback adm:receipts; остальное - adm:rc:<действие>:<id>:
v - карточка; ask - экран подтверждения выпуска; do - выпуск; ok - «чек есть в приложении»
(только unknown); rq - возврат в очередь (для unknown сначала предупреждение); rqdo - возврат
в очередь без предупреждения. Логика и переходы статусов - app/receipts.py. Доступ - только
ADMIN_IDS. Время - UTC, суммы в БД в копейках.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app import receipts as rc
from app.config import ADMIN_IDS
from app.handlers.admin import _rub, _show, _when

router = Router()
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

LIST_LIMIT = 10

_DISABLED_HINT = (
    "Выпуск из бота отключён (NALOG_ISSUE_ENABLED): включается после запуска боевого "
    "магазина ЮKassa."
)
_STATUS_HINTS = {
    "unknown": "Проверьте приложение «Мой налог» (раздел «Продажи»): есть ли там продажа "
               "на эту сумму.",
    "failed": "ФНС отказала, чек не создан.",
    "sending": "Выпуск идёт, обновите экран через несколько секунд.",
}
_OUTCOME_NOTES = {
    "disabled": "Выпуск отключён.",
    "not_claimed": "Чек уже обработан или выпускается.",
    "sent": "✅ Чек выпущен.",
    "failed": "❌ ФНС отказала, чек не создан.",
    "unknown": "⚠️ Результат неизвестен: проверьте приложение «Мой налог».",
    "retry": "Нет соединения с ФНС: запрос не уходил, чек возвращён в очередь.",
}


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _rid(callback: CallbackQuery) -> int:
    return int(callback.data.split(":")[3])


def _label(status: str) -> str:
    return rc.STATUS_LABELS.get(status, status)


def _list_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("⬅️ К чекам", "adm:receipts")]])


def _card_text(card: rc.ReceiptCard, note: str | None) -> str:
    lines = []
    if note:
        lines += [note, ""]
    lines += [
        f"🧾 Чек #{card.id}",
        f"Статус: {_label(card.status)}",
        f"Платёж #{card.payment_id} · {_rub(card.amount)}",
        f"Услуга: {card.service_name}",
        f"Платёж подтверждён (UTC): {_when(card.created_at)}",
    ]
    if card.sent_at:
        lines.append(f"Выпущен (UTC): {_when(card.sent_at)}")
    if card.receipt_url:
        lines.append(f"Ссылка: {card.receipt_url}")
    if card.error:
        lines.append(f"Примечание: {card.error}")
    hint = _STATUS_HINTS.get(card.status)
    if card.status == "pending_review" and not rc.issuing_enabled():
        hint = _DISABLED_HINT
    if hint:
        lines += ["", hint]
    return "\n".join(lines)


def _card_keyboard(card: rc.ReceiptCard) -> InlineKeyboardMarkup:
    rows = []
    if card.status == "pending_review" and rc.issuing_enabled():
        rows.append([_btn("🧾 Выпустить чек", f"adm:rc:ask:{card.id}")])
    elif card.status == "sending":
        rows.append([_btn("🔄 Обновить", f"adm:rc:v:{card.id}")])
    elif card.status == "unknown":
        rows.append([_btn("✅ Чек есть в приложении", f"adm:rc:ok:{card.id}")])
        rows.append([_btn("↩️ Вернуть в очередь", f"adm:rc:rq:{card.id}")])
    elif card.status == "failed":
        rows.append([_btn("↩️ Вернуть в очередь", f"adm:rc:rq:{card.id}")])
    rows.append([_btn("⬅️ К чекам", "adm:receipts")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_card(callback: CallbackQuery, receipt_id: int, note: str | None = None) -> None:
    card = await rc.load_card(receipt_id)
    if card is None:
        await _show(callback, "Чек не найден.", _list_back())
        return
    await _show(callback, _card_text(card, note), _card_keyboard(card))


@router.callback_query(F.data == "adm:receipts")
async def cb_receipts_list(callback: CallbackQuery) -> None:
    await callback.answer()
    total, cards = await rc.list_active(LIST_LIMIT)
    if not total:
        text = "🧾 Чеков к выдаче нет."
    else:
        lines = [f"🧾 Чеки в работе: {total} (время UTC)", ""]
        lines += [
            f"#{c.id} · платёж #{c.payment_id} · {_rub(c.amount)} · {c.service_name} · "
            f"{_label(c.status)} · {_when(c.created_at)}"
            for c in cards
        ]
        if total > len(cards):
            lines.append(f"… и ещё {total - len(cards)}")
        if not rc.issuing_enabled():
            lines += ["", _DISABLED_HINT]
        text = "\n".join(lines)
    rows = [[_btn(f"#{c.id} · {_rub(c.amount)} · {_label(c.status)}", f"adm:rc:v:{c.id}")]
            for c in cards]
    rows.append([_btn("⬅️ Админ-меню", "adm:menu")])
    await _show(callback, text, InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("adm:rc:v:"))
async def cb_receipt_view(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show_card(callback, _rid(callback))


@router.callback_query(F.data.startswith("adm:rc:ask:"))
async def cb_receipt_ask(callback: CallbackQuery) -> None:
    await callback.answer()
    receipt_id = _rid(callback)
    card = await rc.load_card(receipt_id)
    if card is None:
        await _show(callback, "Чек не найден.", _list_back())
        return
    if card.status != "pending_review" or not rc.issuing_enabled():
        await _show_card(callback, receipt_id, "Выпуск сейчас недоступен для этого чека.")
        return
    text = (
        "⚠️ Создать настоящий чек в «Мой налог»?\n\n"
        f"Чек #{card.id} · платёж #{card.payment_id} · {_rub(card.amount)} · "
        f"{card.service_name}\n\n"
        "Чек попадёт в налоговый учёт, отменить его из бота нельзя. Убедитесь, что платёж "
        "настоящий, а не тестовый."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [_btn("✅ Да, выпустить", f"adm:rc:do:{card.id}")],
        [_btn("Отмена", f"adm:rc:v:{card.id}")],
    ])
    await _show(callback, text, kb)


@router.callback_query(F.data.startswith("adm:rc:do:"))
async def cb_receipt_do(callback: CallbackQuery) -> None:
    await callback.answer()
    receipt_id = _rid(callback)
    await _show(callback, f"⏳ Выпускаю чек #{receipt_id}…", _list_back())
    outcome = await rc.issue(callback.bot, receipt_id)
    await _show_card(callback, receipt_id, _OUTCOME_NOTES.get(outcome, outcome))


@router.callback_query(F.data.startswith("adm:rc:ok:"))
async def cb_receipt_ok(callback: CallbackQuery) -> None:
    await callback.answer()
    receipt_id = _rid(callback)
    done = await rc.confirm_manual(receipt_id)
    note = ("✅ Отмечено: чек есть в приложении." if done
            else "Состояние чека изменилось, действие не выполнено.")
    await _show_card(callback, receipt_id, note)


@router.callback_query(F.data.startswith("adm:rc:rq:"))
async def cb_receipt_requeue_ask(callback: CallbackQuery) -> None:
    await callback.answer()
    receipt_id = _rid(callback)
    card = await rc.load_card(receipt_id)
    if card is None:
        await _show(callback, "Чек не найден.", _list_back())
        return
    if card.status == "failed":
        done = await rc.requeue(receipt_id)
        note = ("↩️ Чек возвращён в очередь." if done
                else "Состояние чека изменилось, действие не выполнено.")
        await _show_card(callback, receipt_id, note)
        return
    if card.status != "unknown":
        await _show_card(callback, receipt_id, "В очередь можно вернуть только чек со статусом "
                         "«ошибка» или «результат неизвестен».")
        return
    text = (
        f"⚠️ Вернуть чек #{card.id} в очередь?\n\n"
        "Результат прошлой попытки неизвестен: чек в «Мой налог» мог уже быть создан. "
        f"Сначала откройте приложение (раздел «Продажи») и проверьте, есть ли там продажа "
        f"на {_rub(card.amount)}. Если есть, нажмите «Чек есть в приложении». "
        "Повторный выпуск создаст дубль."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [_btn("↩️ Всё равно вернуть в очередь", f"adm:rc:rqdo:{card.id}")],
        [_btn("⬅️ Назад", f"adm:rc:v:{card.id}")],
    ])
    await _show(callback, text, kb)


@router.callback_query(F.data.startswith("adm:rc:rqdo:"))
async def cb_receipt_requeue(callback: CallbackQuery) -> None:
    await callback.answer()
    receipt_id = _rid(callback)
    done = await rc.requeue(receipt_id)
    note = ("↩️ Чек возвращён в очередь." if done
            else "Состояние чека изменилось, действие не выполнено.")
    await _show_card(callback, receipt_id, note)
