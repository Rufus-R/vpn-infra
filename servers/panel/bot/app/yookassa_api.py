"""Клиент API ЮKassa на httpx, без SDK. См. docs/checkpoint-2026-10-17-payments.md, раздел 10.

Аутентификация — HTTP Basic (shop_id : секретный ключ). Ключ читается из файла
YOOKASSA_SECRET_KEY_FILE и не попадает ни в логи, ни в тексты ошибок.

Проверено 18.10.2026 на тестовом магазине: GET платежа в статусе pending возвращает
confirmation.confirmation_url; поля expires_at в ответе нет (возраст платежа ограничивается
на стороне бота). Для боевого магазина не проверялось.
"""
from __future__ import annotations
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx

from app.config import YOOKASSA_SECRET_KEY_FILE, YOOKASSA_SHOP_ID

API_BASE = "https://api.yookassa.ru/v3"
DESCRIPTION_MAX = 128
# Идентификатор платежа ЮKassa (UUID-подобный). Проверяется до подстановки в путь запроса:
# id приходит в теле вебхука, а тело уведомления не подписано.
_PAYMENT_ID_RE = re.compile(r"^[0-9a-zA-Z-]{1,64}$")


class YooKassaError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def format_amount(kopecks: int) -> dict:
    """Сумма из копеек в формат ЮKassa: {"value": "200.00", "currency": "RUB"}."""
    if kopecks <= 0:
        raise ValueError("сумма платежа должна быть положительной")
    return {"value": f"{kopecks // 100}.{kopecks % 100:02d}", "currency": "RUB"}


def kopecks_from_amount(amount: dict) -> int:
    """Сумма из ответа ЮKassa в копейки (Decimal, без float)."""
    try:
        value = Decimal(str(amount["value"])) * 100
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise YooKassaError("некорректное поле amount в ответе ЮKassa") from exc
    if value != value.to_integral_value():
        raise YooKassaError("сумма в ответе ЮKassa не кратна копейке")
    return int(value)


class YooKassaClient:
    def __init__(self) -> None:
        if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY_FILE:
            raise YooKassaError(
                "ЮKassa не настроена: задайте YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY_FILE"
            )
        try:
            secret = Path(YOOKASSA_SECRET_KEY_FILE).read_text().strip()
        except OSError as exc:
            raise YooKassaError("не удалось прочитать файл секретного ключа ЮKassa") from exc
        if not secret:
            raise YooKassaError("файл секретного ключа ЮKassa пуст")
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            auth=httpx.BasicAuth(YOOKASSA_SHOP_ID, secret),
            timeout=15.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _call(self, method: str, path: str, **kwargs) -> dict:
        try:
            resp = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise YooKassaError(f"{method} {path}: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            code = description = None
            try:
                body = resp.json()
                code = body.get("code")
                description = body.get("description")
            except (ValueError, AttributeError):
                pass
            raise YooKassaError(
                f"{method} {path}: HTTP {resp.status_code} code={code!r} "
                f"description={description!r}",
                status_code=resp.status_code,
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise YooKassaError(f"{method} {path}: ответ не является JSON") from exc
        if not isinstance(data, dict):
            raise YooKassaError(f"{method} {path}: неожиданная структура ответа")
        return data

    async def create_payment(self, *, amount_kopecks: int, description: str,
                             return_url: str, local_payment_id: int,
                             idempotence_key: str) -> dict:
        """Создать платёж с автоматическим списанием (capture=true). Повтор с тем же
        idempotence_key и теми же параметрами вернёт тот же платёж (в том числе после
        таймаута). local_payment_id пишется в metadata.payment_id для сверки."""
        payload = {
            "amount": format_amount(amount_kopecks),
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": description[:DESCRIPTION_MAX],
            "metadata": {"payment_id": str(local_payment_id)},
        }
        return await self._call(
            "POST", "/payments", json=payload,
            headers={"Idempotence-Key": idempotence_key},
        )

    async def get_payment(self, provider_payment_id: str) -> dict:
        if not isinstance(provider_payment_id, str) or not _PAYMENT_ID_RE.match(provider_payment_id):
            raise YooKassaError("некорректный идентификатор платежа")
        return await self._call("GET", f"/payments/{provider_payment_id}")
