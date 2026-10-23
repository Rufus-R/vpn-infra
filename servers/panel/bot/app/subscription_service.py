"""Единая точка выдачи и продления клиента Panel: один клиент на пользователя
(docs/checkpoint-2026-10-22-subscriptions.md). Используется триалом, оплатой
(app/payments.py) и в дальнейшем бонусом по рефералке.

Срок на Panel всегда выставляется АБСОЛЮТНОЙ датой (а не добавлением дней): повторная
отправка того же значения ничего не прибавляет второй раз. Целевая дата считается один раз
(compute_target_end) и вызывающий код сохраняет её до обращения к Panel.
"""
from __future__ import annotations
import asyncio
import datetime as dt
import logging
from dataclasses import dataclass

import httpx
from sqlalchemy import select

from app.config import REALITY_INBOUND_ID, SUB_BASE_URL
from app.db.base import async_session
from app.db.models import Plan, Subscription, User
from app.panel_api import PanelApiClient, PanelApiError

logger = logging.getLogger("subscription_service")

# Бот — один процесс, блокировок в памяти достаточно.
_USER_LOCKS: dict[int, asyncio.Lock] = {}


def user_lock(user_id: int) -> asyncio.Lock:
    """Блокировка операций одного пользователя (триал, оплата, бонус, понижение лимита)."""
    lock = _USER_LOCKS.get(user_id)
    if lock is None:
        lock = _USER_LOCKS[user_id] = asyncio.Lock()
    return lock


def client_email(tg_id: int) -> str:
    return f"tg{tg_id}@netru.bot"


def _ms(value: dt.datetime) -> int:
    """Наивный UTC (как utcnow() в БД бота) -> миллисекунды epoch. НЕ value.timestamp():
    для наивной даты он берёт ЛОКАЛЬНЫЙ пояс сервера (на Panel — MSK) и сдвигает срок."""
    return int(value.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def _from_ms(ms: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).replace(tzinfo=None)


@dataclass
class ApplyResult:
    email: str
    uuid: str | None
    sub_id: str | None
    sub_url: str | None
    created: bool            # клиент создан этим вызовом
    already_applied: bool    # на Panel срок уже не меньше целевого (повтор после сбоя)
    limit_ip: int            # лимит устройств на Panel после операции
    downgrade_to: int | None = None            # отложенное понижение лимита (устройств)
    downgrade_base: dt.datetime | None = None  # когда понижать: конец уже оплаченного периода


async def compute_target_end(panel: PanelApiClient, tg_id: int, days: int) -> dt.datetime:
    """Целевая дата окончания: max(сейчас, текущий срок клиента на Panel) + days.
    Источник истины — Panel (ручные правки админа не затираются). Клиента нет — от «сейчас».
    Бессрочный клиент (expiryTime=0) — ошибка: срок автоматически не меняем."""
    now = dt.datetime.utcnow()
    email = client_email(tg_id)
    base = now
    if await panel.client_exists(email):
        client = (await panel.get_client(email))["client"]
        expiry_ms = int(client.get("expiryTime") or 0)
        if expiry_ms <= 0:
            raise PanelApiError(
                f"клиент {email} бессрочный (expiryTime=0): срок автоматически не меняется"
            )
        base = max(now, _from_ms(expiry_ms))
    return base + dt.timedelta(days=days)


async def apply_period(panel: PanelApiClient, *, user: User, plan: Plan,
                       target_end_at: dt.datetime, kind: str) -> ApplyResult:
    """Создать клиента (если нет) или выставить ему срок target_end_at.
    kind='paid' — оплата (лимит устройств по тарифу), kind='trial' — триал/бонус (лимит
    существующего клиента не меняется; новому клиенту — по тарифу).
    Поле comment клиента Panel — название тарифа: шаблон примечания подписки показывает его
    в имени профиля. Новому клиенту оно ставится всегда, существующему — только при оплате
    (триал и бонус название платного тарифа не затирают)."""
    if kind not in ("paid", "trial"):
        raise ValueError(f"неизвестный kind: {kind}")
    if REALITY_INBOUND_ID is None:
        raise PanelApiError("REALITY_INBOUND_ID не задан")

    email = client_email(user.tg_id)
    now_ms = _ms(dt.datetime.utcnow())
    target_ms = _ms(target_end_at)
    created = False
    already_applied = False
    downgrade_to: int | None = None
    downgrade_base: dt.datetime | None = None

    if not await panel.client_exists(email):
        await panel.add_client(
            email=email, limit_ip=plan.device_count, total_gb=0,
            expiry_time_ms=target_ms, inbound_ids=[REALITY_INBOUND_ID],
            tg_id=user.tg_id, comment=plan.name,
        )
        created = True
    else:
        current = (await panel.get_client(email))["client"]
        current_ms = int(current.get("expiryTime") or 0)
        current_limit = int(current.get("limitIp") or 0)
        if current_ms >= target_ms:
            already_applied = True
        else:
            limit = current_limit
            if kind == "paid":
                period_active = current_ms > now_ms
                if current_limit <= 0 or plan.device_count >= current_limit or not period_active:
                    limit = plan.device_count
                else:
                    # Тариф меньше текущего лимита, а оплаченный период ещё идёт:
                    # лимит остаётся до его окончания, понижение — отложенное.
                    downgrade_to = plan.device_count
                    downgrade_base = _from_ms(current_ms)
            changes = {"expiryTime": target_ms, "enable": True, "limitIp": limit}
            if kind == "paid":
                changes["comment"] = plan.name
            await panel.update_client_safe(email, **changes)

    client = (await panel.get_client(email))["client"]
    sub_id = client.get("subId")
    return ApplyResult(
        email=email,
        uuid=client.get("uuid"),
        sub_id=sub_id,
        sub_url=f"{SUB_BASE_URL}{sub_id}" if sub_id and SUB_BASE_URL else None,
        created=created,
        already_applied=already_applied,
        limit_ip=int(client.get("limitIp") or 0),
        downgrade_to=downgrade_to,
        downgrade_base=downgrade_base,
    )


async def save_subscription(session, user: User, plan: Plan, result: ApplyResult,
                            target_end_at: dt.datetime, kind: str) -> Subscription:
    """Синхронизировать единственную строку Subscription пользователя с Panel.
    Коммит — на вызывающем."""
    now = dt.datetime.utcnow()
    sub = (await session.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )).scalar_one_or_none()
    if sub is None:
        sub = Subscription(
            user_id=user.id, panel_client_email=result.email, plan_id=plan.id,
            start_at=now, end_at=target_end_at,
            status="trial" if kind == "trial" else "active",
            inbound_ids=[REALITY_INBOUND_ID],
        )
        session.add(sub)
    else:
        if kind == "paid":
            if sub.end_at <= now:
                sub.start_at = now
            sub.plan_id = plan.id
            sub.status = "active"
        # триал на существующей подписке: план и статус не меняются, только срок
        sub.end_at = max(sub.end_at, target_end_at)
    sub.panel_client_email = result.email
    sub.panel_client_uuid = result.uuid
    sub.panel_client_sub_id = result.sub_id
    sub.inbound_ids = [REALITY_INBOUND_ID]

    if kind == "paid" and not result.already_applied:
        if result.downgrade_to is not None:
            if sub.next_device_count is None:
                sub.next_device_at = result.downgrade_base
            sub.next_device_count = result.downgrade_to
        else:
            sub.next_device_count = None
            sub.next_device_at = None
    return sub


async def apply_due_downgrades() -> None:
    """Применить отложенное понижение лимита устройств (next_device_at наступил)."""
    now = dt.datetime.utcnow()
    async with async_session() as session:
        rows = (await session.execute(
            select(Subscription).where(
                Subscription.next_device_at.is_not(None),
                Subscription.next_device_at <= now,
            )
        )).scalars().all()
        if not rows:
            return
        panel = PanelApiClient()
        try:
            for sub in rows:
                async with user_lock(sub.user_id):
                    await session.refresh(sub)
                    if sub.next_device_at is None or sub.next_device_at > now:
                        continue  # за это время его отменила новая покупка
                    try:
                        await panel.update_client_safe(
                            sub.panel_client_email, limitIp=sub.next_device_count,
                        )
                    except (PanelApiError, httpx.HTTPError):
                        logger.exception("понижение лимита устройств: сбой %s",
                                         sub.panel_client_email)
                        continue
                    sub.next_device_count = None
                    sub.next_device_at = None
                    await session.commit()
        finally:
            await panel.close()
