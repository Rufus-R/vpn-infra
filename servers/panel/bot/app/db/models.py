"""Схема БД бота — см. docs/commercial/bot.md, раздел 'Схема данных'."""
from __future__ import annotations
import datetime as dt
from sqlalchemy import String, Integer, BigInteger, Boolean, ForeignKey, DateTime, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    # 10.10.2026: сбор номера телефона в сценарии триала убран (решение оператора —
    # антифрод держится только на tg_id/trial_used, см. docs/commercial/overview.md,
    # "Принятые риски"). Колонка оставлена в схеме на случай будущего сценария
    # (например, доставка чека НПД при оплате без "Чеков от ЮKassa"), новым кодом
    # не заполняется.
    phone_number: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    referrer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False)
    # Согласие на обработку ПДн (ст. 9 152-ФЗ) — фиксируется нажатием кнопки
    # "Я согласен" при первом /start, см. app/handlers/start.py. До согласия
    # пользователю недоступны разделы меню (require_consent).
    privacy_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    privacy_accepted_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")
    payments: Mapped[list["Payment"]] = relationship(back_populates="user")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    duration_days: Mapped[int] = mapped_column(Integer)
    device_count: Mapped[int] = mapped_column(Integer)  # -> limitIp при создании клиента
    price: Mapped[int] = mapped_column(Integer)  # в копейках
    discount_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Добавлено 09.10.2026 для раздела "Тарифы" (UI-текст карточки). Существующая таблица
    # "plans" на Panel не содержит эту колонку физически — добавляется идемпотентной
    # dev-миграцией в db/base.py при старте (ALTER TABLE ... ADD COLUMN), до Alembic.
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    panel_client_email: Mapped[str] = mapped_column(String(128), unique=True)
    panel_client_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    panel_client_sub_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    inbound_ids: Mapped[list] = mapped_column(JSON, default=list)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    start_at: Mapped[dt.datetime] = mapped_column(DateTime)
    end_at: Mapped[dt.datetime] = mapped_column(DateTime)
    # trial/active/expired/pending_payment/rejected (свободная строка, без enum —
    # см. комментарий в handlers/tariffs.py про fallback-оплату, 09.10.2026)
    status: Mapped[str] = mapped_column(String(16), default="trial")

    user: Mapped[User] = relationship(back_populates="subscriptions")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("uq_payments_provider_payment_id", "provider_payment_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id"), nullable=True)
    amount: Mapped[int] = mapped_column(Integer)  # в копейках
    provider: Mapped[str] = mapped_column(String(16))  # manual/yookassa
    provider_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/confirmed/rejected
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="payments")


class ReferralBonus(Base):
    __tablename__ = "referral_bonuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    referred_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    bonus_days: Mapped[int] = mapped_column(Integer)
    granted_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class SupportMessage(Base):
    """Раздел «Поддержка» — см. docs/commercial/bot.md, 'Сценарий: поддержка'.
    direction='user': копия сообщения пользователя, разосланная ОДНОМУ конкретному
    админу (admin_tg_id/admin_message_id — чтобы поймать его Reply). При нескольких
    ADMIN_IDS на одно обращение создаётся несколько строк (по одной на админа),
    сгруппированных полем source_message_id (message_id ОРИГИНАЛЬНОГО сообщения
    пользователя, не пересланной копии) — пара (user_id, source_message_id)
    однозначно идентифицирует "тред" обращения.
    direction='admin': ответ админа, переслан пользователю (для истории/аудита,
    admin_tg_id/admin_message_id/source_message_id не используются).
    answered: при ответе ЛЮБОГО админа помечаются True ВСЕ строки треда (не только
    та, на которую был Reply) — остальным админам редактируется их копия сообщения
    с пометкой "уже отвечено", чтобы снизить риск дублирующего ответа (не исключает
    полностью гонку при одновременном ответе двух админов, см. bot.md)."""
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    direction: Mapped[str] = mapped_column(String(8))
    body: Mapped[str] = mapped_column(String(4096))
    source_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    admin_tg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    admin_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class Receipt(Base):
    """Чек самозанятого (НПД) по платежу ЮKassa — см. docs/checkpoint-2026-10-17-payments.md.
    Один платёж — один чек (UNIQUE payment_id). amount — в копейках, как payments.amount.
    status: pending_review (ждёт решения админа) / sending (запрос к «Мой налог» отправлен) /
    sent / failed / unknown (результат запроса неизвестен — не повторять автоматически) /
    rejected / cancelled (свободная строка, без enum)."""
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="pending_review")
    amount: Mapped[int] = mapped_column(Integer)
    service_name: Mapped[str] = mapped_column(String(255))
    receipt_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    receipt_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
