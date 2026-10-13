"""Раздел «Мои подписки». См. docs/commercial/bot.md, 'Сценарий: мои подписки'.

Статус читается напрямую через API Panel (GET /clients/get/{email}) — актуальные
enable/expiryTime/totalGB/usedTraffic, а не из локальной БД бота (локальная БД
хранит только plan_id/start_at/end_at на момент создания, не отражает последующие
изменения на панели — ручной bulkAdjust/bulkDisable администратором и т.п.).
"""
import datetime as dt

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.config import SUB_BASE_URL
from app.db.base import async_session
from app.db.models import Subscription, Plan
from app.handlers.start import require_consent, CONSENT_TEXT
from app.keyboards import consent_keyboard, subscriptions_keyboard
from app.panel_api import PanelApiClient, PanelApiError

router = Router()


def _format_remaining(expiry_ms: int) -> str:
    if expiry_ms <= 0:
        return "без ограничения по сроку"
    end = dt.datetime.utcfromtimestamp(expiry_ms / 1000)
    now = dt.datetime.utcnow()
    end_str = end.strftime("%d.%m.%Y")
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
        result = await session.execute(
            select(Subscription, Plan)
            .join(Plan, Subscription.plan_id == Plan.id)
            .where(Subscription.user_id == user.id)
            .where(Subscription.status.in_(["trial", "active"]))
            .order_by(Subscription.end_at.desc())
        )
        rows = result.all()

    if not rows:
        await callback.message.answer(
            "У вас пока нет подписок. Попробуйте бесплатный период или выберите тариф "
            "в главном меню."
        )
        return

    panel = PanelApiClient()
    blocks = []
    links: list[tuple[str, str]] = []
    try:
        for subscription, plan in rows:
            status_badge = "🎁 Пробная" if subscription.status == "trial" else "✅ Платная"
            sub_id = subscription.panel_client_sub_id
            try:
                data = await panel.get_client(subscription.panel_client_email)
                client = data["client"]
                enable = client.get("enable", False)
                expiry_ms = client.get("expiryTime", 0)
                total_gb = client.get("totalGB", 0)
                used_bytes = data.get("usedTraffic", 0)
                if not enable:
                    status_badge = "❌ Отключена"
                remaining = _format_remaining(expiry_ms)
                traffic = _format_traffic(total_gb, used_bytes)
                sub_id = client.get("subId") or sub_id
            except PanelApiError:
                remaining = "статус недоступен (ошибка панели)"
                traffic = "—"

            block = (
                f"{status_badge} <b>{plan.name}</b>\n"
                f"Срок: {remaining}\n"
                f"Трафик: {traffic}"
            )
            blocks.append(block)
            if sub_id and SUB_BASE_URL:
                links.append((plan.name, f"{SUB_BASE_URL}{sub_id}"))
    finally:
        await panel.close()

    text = "\n\n".join(blocks)
    await callback.message.answer(
        text, reply_markup=subscriptions_keyboard(links), parse_mode="HTML"
    )
