"""Схема БД бота — см. docs/commercial/bot.md, раздел 'Схема данных'."""
from __future__ import annotations
import datetime as dt
from sqlalchemy import String, Integer, BigInteger, Boolean, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    referrer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False)
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
    status: Mapped[str] = mapped_column(String(16), default="trial")  # trial/active/expired

    user: Mapped[User] = relationship(back_populates="subscriptions")


class Payment(Base):
    __tablename__ = "payments"

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
