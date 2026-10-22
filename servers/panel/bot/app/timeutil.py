"""Отображение времени пользователям бота (МСК). В БД и расчётах — наивный UTC (utcnow()).
Россия не переводит часы на летнее время, поэтому достаточно фиксированного сдвига +3 ч
(tzdata на сервере не нужен). Админ-меню остаётся в UTC (app/handlers/admin.py)."""
from __future__ import annotations
import datetime as dt

MSK = dt.timezone(dt.timedelta(hours=3))


def to_msk(value: dt.datetime) -> dt.datetime:
    """Наивный UTC -> aware МСК."""
    return value.replace(tzinfo=dt.timezone.utc).astimezone(MSK)


def fmt_msk(value: dt.datetime, fmt: str = "%d.%m.%Y") -> str:
    return to_msk(value).strftime(fmt)
