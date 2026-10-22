"""Раздел «Мои подписки». См. docs/commercial/bot.md, 'Сценарий: мои подписки'.

Статус читается напрямую через API Panel (GET /clients/get/{email}) — актуальные
enable/expiryTime/totalGB/usedTraffic, а не из локальной БД бота (локальная БД
хранит только plan_id/start_at/end_at на момент создания, не отражает последующие
изменения на панели — ручной bulkAdjust/bulkDisable администратором и т.п.).

С 22.10.2026: у пользователя одна своя подписка (один клиент Panel) плюс, при наличии,
привязанные вручную клиенты (таблица linked_clients) — они остаются со своими ссылками.
"""
import datetime as dt
from html import escape

import httpx
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.config import SUB_BASE_URL
from app.db.base import async_session
from app.db.models import LinkedClient, Plan, Subscription
from app.handlers.start import require_consent, CONSENT_TEXT
from app.keyboards import consent_keyboard, subscriptions_keyboard
from app.panel_api import PanelApiClient, PanelApiError
from app.timeutil import fmt_msk

router = Router()

DEFAULT_LINKED_LABEL = "Дополнительное подключение"


def _format_remaining(expiry_ms: int) -> str:
    if expiry_ms <= 0:
        return "без ограничения по сроку"
    end = dt.datetime.utcfromtimestamp(expiry_ms / 1000)
    now = dt.datetime.utcnow()
    end_str = fmt_msk(end)
    if end <= now:
        return f"❌ истекла {end_str}"
    days_left = (end - now).days
    if days_left <= 3:
        return f"⚠️ истекает через {days_left} дн. ({end_str})"
    return f"действует до {end_str}"


def _format_traffic(total_gb: int, used_bytes: int) -> str:
    if total_gb <= 0:
        return "без ограничения трафика"
    used_gb = used_bytes / (1024 ** 3)
    total_gb_h = total_gb / (1024 ** 3)
    return f"{used_gb:.1f} / {total_gb_h:.0f} ГБ"


@router.callback_query(F.data == "menu:subs")
async def cb_subs(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await require_consent(callback.from_user.id)
    if user is None:
        await callback.message.answer(CONSENT_TEXT, reply_markup=consent_keyboard())
        return

    async with async_session() as session:
        own = (await session.execute(
            select(Subscription, Plan)
            .join(Plan, Subscription.plan_id == Plan.id)
            .where(Subscription.user_id == user.id)
            .where(Subscription.status.in_(["trial", "active"]))
            .where(Subscription.end_at > dt.datetime.utcnow())
        )).first()
        linked = (await session.execute(
            select(LinkedClient).where(LinkedClient.user_id == user.id)
            .order_by(LinkedClient.id)
        )).scalars().all()

    if own is None and not linked:
        await callback.message.answer(
            "Действующих подписок нет. Тарифы и бесплатный пробный период "
            "(если вы ещё не использовали его) — в главном меню."
        )
        return

    panel = PanelApiClient()
    blocks: list[str] = []
    links: list[tuple[str, str]] = []
    try:
        if own is not None:
            subscription, plan = own
            status_badge = "🎁 Пробная" if subscription.status == "trial" else "✅ Платная"
            sub_id = subscription.panel_client_sub_id
            devices_line = ""
            try:
                data = await panel.get_client(subscription.panel_client_email)
                client = data["client"]
                if not client.get("enable", False):
                    status_badge = "❌ Отключена"
                remaining = _format_remaining(client.get("expiryTime", 0))
                traffic = _format_traffic(client.get("totalGB", 0), data.get("usedTraffic", 0))
                sub_id = client.get("subId") or sub_id
                limit_ip = int(client.get("limitIp") or 0)
                if limit_ip > 0:
                    devices_line = f"\nУстройств: {limit_ip}"
                    if subscription.next_device_count and subscription.next_device_at:
                        devices_line += (
                            f" (с {fmt_msk(subscription.next_device_at)} — "
                            f"{subscription.next_device_count})"
                        )
            except (PanelApiError, httpx.HTTPError):
                remaining = "статус недоступен (ошибка панели)"
                traffic = "—"
            blocks.append(
                f"{status_badge} <b>{escape(plan.name)}</b>\n"
                f"Срок: {remaining}{devices_line}\n"
                f"Трафик: {traffic}"
            )
            if sub_id and SUB_BASE_URL:
                links.append((plan.name, f"{SUB_BASE_URL}{sub_id}"))

        for item in linked:
            name = item.label or DEFAULT_LINKED_LABEL
            sub_id = None
            try:
                data = await panel.get_client(item.panel_client_email)
                client = data["client"]
                badge = "✅" if client.get("enable", False) else "❌ Отключено"
                remaining = _format_remaining(client.get("expiryTime", 0))
                traffic = _format_traffic(client.get("totalGB", 0), data.get("usedTraffic", 0))
                sub_id = client.get("subId")
            except (PanelApiError, httpx.HTTPError):
                badge = "✅"
                remaining = "статус недоступен (ошибка панели)"
                traffic = "—"
            blocks.append(
                f"{badge} <b>{escape(name)}</b>\n"
                f"Срок: {remaining}\n"
                f"Трафик: {traffic}"
            )
            if sub_id and SUB_BASE_URL:
                links.append((name, f"{SUB_BASE_URL}{sub_id}"))
    finally:
        await panel.close()

    await callback.message.answer(
        "\n\n".join(blocks), reply_markup=subscriptions_keyboard(links), parse_mode="HTML"
    )
