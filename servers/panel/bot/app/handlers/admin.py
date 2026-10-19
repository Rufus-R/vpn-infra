"""Меню администратора (MVP, 19.10.2026).

Доступ только для ADMIN_IDS: фильтр стоит на всём роутере (router.callback_query.filter),
кнопка «🛠 Админ» в главном меню — лишь удобство. Префикс callback-данных adm: (не admin:,
прежние admin:confirm:/admin:reject: удалены 19.10.2026).
В списках только внутренние user_id, без username (решение оператора 19.10.2026).
Время — UTC, как в БД. Суммы в БД хранятся в копейках.
"""
from __future__ import annotations

import datetime as dt
import time

import httpx
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from sqlalchemy import func, select

from app.config import ADMIN_IDS
from app.db.base import async_session
from app.db.models import Payment, Receipt, Subscription, SupportMessage, User
from app.keyboards import admin_back_keyboard, admin_menu_keyboard
from app.panel_api import PanelApiClient, PanelApiError

router = Router()
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


def _rub(kopecks: int) -> str:
    return f"{kopecks // 100} ₽"


def _when(value: dt.datetime | None) -> str:
    return value.strftime("%d.%m %H:%M") if value else "—"


async def _show(callback: CallbackQuery, text: str, kb: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        await callback.message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "adm:menu")
async def cb_admin_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show(callback, "🛠 Администрирование", admin_menu_keyboard())


@router.callback_query(F.data == "adm:stats")
async def cb_admin_stats(callback: CallbackQuery) -> None:
    await callback.answer()
    now = dt.datetime.utcnow()
    async with async_session() as session:
        users_total = (await session.execute(select(func.count(User.id)))).scalar_one()
        consented = (await session.execute(
            select(func.count(User.id)).where(User.privacy_accepted.is_(True)))).scalar_one()
        trials_used = (await session.execute(
            select(func.count(User.id)).where(User.trial_used.is_(True)))).scalar_one()
        paid_now = (await session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.status == "active", Subscription.end_at > now))).scalar_one()
        trial_now = (await session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.status == "trial", Subscription.end_at > now))).scalar_one()
        sub_rows = (await session.execute(
            select(Subscription.status, func.count()).group_by(Subscription.status)
            .order_by(Subscription.status))).all()
        pay_rows = (await session.execute(
            select(Payment.status, func.count(), func.coalesce(func.sum(Payment.amount), 0))
            .group_by(Payment.status).order_by(Payment.status))).all()

    lines = [
        "📊 Статистика",
        "",
        f"Пользователей: {users_total} (согласие на ПДн: {consented}, триал брали: {trials_used})",
        f"Действующих сейчас: платных {paid_now}, триалов {trial_now}",
        "",
        "Подписки по статусам:",
    ]
    lines += [f"• {status}: {count}" for status, count in sub_rows] or ["• нет"]
    lines += ["", "Платежи по статусам:"]
    lines += [f"• {status}: {count} на {_rub(total)}" for status, count, total in pay_rows] or ["• нет"]
    await _show(callback, "\n".join(lines), admin_back_keyboard())


@router.callback_query(F.data == "adm:payments")
async def cb_admin_payments(callback: CallbackQuery) -> None:
    await callback.answer()
    async with async_session() as session:
        rows = (await session.execute(
            select(Payment).order_by(Payment.id.desc()).limit(10))).scalars().all()
    if not rows:
        text = "💳 Платежей пока нет."
    else:
        lines = ["💳 Последние платежи (время UTC):", ""]
        lines += [
            f"#{p.id} · user {p.user_id} · {_rub(p.amount)} · {p.status} · "
            f"{p.provider} · {_when(p.created_at)}"
            for p in rows
        ]
        text = "\n".join(lines)
    await _show(callback, text, admin_back_keyboard())


@router.callback_query(F.data == "adm:receipts")
async def cb_admin_receipts(callback: CallbackQuery) -> None:
    await callback.answer()
    async with async_session() as session:
        total = (await session.execute(
            select(func.count(Receipt.id)).where(Receipt.status == "pending_review"))).scalar_one()
        rows = (await session.execute(
            select(Receipt, Payment).join(Payment, Receipt.payment_id == Payment.id)
            .where(Receipt.status == "pending_review").order_by(Receipt.id).limit(20))).all()
    if not total:
        text = "🧾 Чеков к выдаче нет."
    else:
        lines = [
            f"🧾 Чеков к выдаче: {total} (ждут ручной выдачи в «Мой налог»; время UTC)",
            "",
        ]
        lines += [
            f"чек #{r.id} · платёж #{p.id} · {_rub(r.amount)} · {r.service_name} · "
            f"{_when(r.created_at)}"
            for r, p in rows
        ]
        if total > len(rows):
            lines.append(f"… и ещё {total - len(rows)}")
        text = "\n".join(lines)
    await _show(callback, text, admin_back_keyboard())


@router.callback_query(F.data == "adm:support")
async def cb_admin_support(callback: CallbackQuery) -> None:
    await callback.answer()
    admin_id = callback.from_user.id
    base = (SupportMessage.direction == "user", SupportMessage.answered.is_(False))
    async with async_session() as session:
        threads = (await session.execute(
            select(func.count()).select_from(
                select(SupportMessage.user_id, SupportMessage.source_message_id)
                .where(*base).distinct().subquery()))).scalar_one()
        mine_total = (await session.execute(
            select(func.count(SupportMessage.id)).where(
                *base, SupportMessage.admin_tg_id == admin_id))).scalar_one()
        mine = (await session.execute(
            select(SupportMessage).where(*base, SupportMessage.admin_tg_id == admin_id)
            .order_by(SupportMessage.created_at).limit(10))).scalars().all()
    if not threads:
        text = "📩 Необработанных обращений нет."
    else:
        lines = [
            f"📩 Необработанных обращений: {threads}; в вашей очереди: {mine_total}.",
            "Для ответа откройте карточки командой /queue и ответьте на них через Reply.",
            "",
        ]
        for m in mine:
            body = m.body if len(m.body) <= 80 else m.body[:80] + "…"
            lines.append(f"• user {m.user_id} · {_when(m.created_at)} · {body}")
        text = "\n".join(lines)
    await _show(callback, text, admin_back_keyboard())


# Сводка summary из GET /clients/list/paged: для каждого показателя Panel отдаёт и счётчик
# (xCount), и список email (ограничен 200) — берём счётчик, иначе число или длину списка.
_PANEL_SUMMARY = (
    ("total", "Всего клиентов"),
    ("active", "Активных"),
    ("online", "Сейчас онлайн"),
    ("depleted", "Исчерпаны (срок или трафик)"),
    ("expiring", "Скоро истекают"),
    ("deactive", "Отключены"),
)


def _summary_lines(summary: dict) -> list[str]:
    lines = []
    for key, label in _PANEL_SUMMARY:
        value = summary.get(f"{key}Count", summary.get(key))
        if isinstance(value, bool):
            continue
        if isinstance(value, list):
            value = len(value)
        if isinstance(value, (int, float)):
            lines.append(f"• {label}: {int(value)}")
    return lines


@router.callback_query(F.data == "adm:panel")
async def cb_admin_panel(callback: CallbackQuery) -> None:
    await callback.answer()
    panel = PanelApiClient()
    started = time.monotonic()
    try:
        data = await panel._call("GET", "/clients/list/paged", params={"page": 1, "pageSize": 1})
    except (PanelApiError, httpx.HTTPError) as exc:
        text = f"🩺 Panel: ошибка ({type(exc).__name__})."
        if isinstance(exc, httpx.HTTPStatusError):
            text += f" HTTP {exc.response.status_code}."
    else:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        lines = [f"🩺 Panel: ответ получен за {elapsed_ms} мс, success=true."]
        obj = data.get("obj")
        summary = obj.get("summary") if isinstance(obj, dict) else None
        if isinstance(summary, dict):
            lines += _summary_lines(summary)
        text = "\n".join(lines)
    finally:
        await panel.close()
    await _show(callback, text, admin_back_keyboard())
