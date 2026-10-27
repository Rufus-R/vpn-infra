"""Выпуск чеков самозанятого через «Мой налог» и проверка токена.

См. docs/checkpoint-2026-10-17-payments.md, разделы 19-22. Клиент nalogo 1.2.0, один
экземпляр на процесс: ФНС ротирует refresh-токен при каждом обновлении, второй клиент с тем же
token.json испортил бы сессию.

issue_receipt() не бросает исключений: возвращает IssueResult со статусом
  sent    - чек создан (есть receipt_uuid; receipt_url, если известен ИНН);
  failed  - ФНС ответила явным отказом или данные не прошли проверку: чек не создан;
  unknown - результат запроса неизвестен (таймаут, обрыв после отправки, 5xx, ответ без
            идентификатора чека): автоповтор запрещён, решает админ;
  retry   - запрос заведомо не ушёл (нет соединения): можно вернуть чек в очередь.
POST /income не идемпотентен, поэтому любые сомнения - это unknown, а не retry.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot
from nalogo.client import Client
from nalogo.dto.income import (
    AtomDateTime, IncomeClient, IncomeRequest, IncomeServiceItem, PaymentType,
)
from nalogo.exceptions import (
    ClientException, ConnectionException, DomainException, ForbiddenException,
    NetworkException, NotFoundException, RateLimitException, ServerException,
    UnauthorizedException, UnprocessableEntityException, ValidationException,
)

from app.config import ADMIN_IDS, NALOG_STATE_DIR

logger = logging.getLogger("nalog")

ITEM_PREFIX = "Штиль: "
RECEIPT_URL_TEMPLATE = "https://lknpd.nalog.ru/api/v1/receipt/{inn}/{uuid}/print"

CHECK_HOUR_MSK = 9
FIRST_CHECK_DELAY_SEC = 30
UNAVAILABLE_ATTEMPTS = 3
UNAVAILABLE_PAUSE_SEC = 600
_MSK = ZoneInfo("Europe/Moscow")

_client: Client | None = None
_inn: str | None = None
_token_state: str | None = None  # None (не проверялся) / ok / rejected / unavailable


@dataclass
class IssueResult:
    status: str
    receipt_uuid: str | None = None
    receipt_url: str | None = None
    error: str | None = None


def nalog_enabled() -> bool:
    return bool(NALOG_STATE_DIR)


def _short(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)[:200]}"[:255]


def _get_client() -> Client:
    global _client
    if _client is None:
        if not NALOG_STATE_DIR:
            raise RuntimeError("NALOG_STATE_DIR не задан")
        state_dir = Path(NALOG_STATE_DIR)
        device_id = (state_dir / "device_id").read_text(encoding="utf-8").strip()
        if not device_id:
            raise RuntimeError("файл device_id пуст")
        _client = Client(storage_path=str(state_dir / "token.json"), device_id=device_id)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _get_inn(client: Client) -> str | None:
    global _inn
    if _inn:
        return _inn
    token = await client.auth_provider.get_token() or {}
    profile = token.get("profile")
    inn = profile.get("inn") if isinstance(profile, dict) else None
    if not inn:
        inn = (await client.user().get()).get("inn")
    if inn:
        _inn = str(inn)
    return _inn


def _build_payload(service_name: str, amount_kopecks: int,
                   operation_time: dt.datetime) -> dict:
    """operation_time - момент подтверждения платежа; наивное значение считается UTC."""
    if amount_kopecks <= 0:
        raise ValueError("сумма должна быть положительной")
    moment = operation_time
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    moment = min(moment, dt.datetime.now(dt.timezone.utc))
    item = IncomeServiceItem(
        name=ITEM_PREFIX + service_name,
        amount=Decimal(amount_kopecks).scaleb(-2),
        quantity=Decimal(1),
    )
    request = IncomeRequest(
        operation_time=AtomDateTime.from_datetime(moment),
        request_time=AtomDateTime.now(),
        services=[item],
        total_amount=str(item.get_total_amount()),
        client=IncomeClient(),
        payment_type=PaymentType.ACCOUNT,
    )
    payload = request.model_dump()
    # ФНС (проверено 27.10.2026 боем) принимает paymentType только CASH или WIRE,
    # значение ACCOUNT даёт 400 ValidationException. В enum nalogo 1.2.0 значения
    # WIRE нет (только CASH/ACCOUNT), поэтому после сериализации подменяем:
    # оплата картой через ЮKassa — безналичный расчёт = WIRE.
    payload["paymentType"] = "WIRE"
    return payload


async def _issue_receipt(service_name: str, amount_kopecks: int,
                         operation_time: dt.datetime) -> IssueResult:
    try:
        client = _get_client()
    except (OSError, RuntimeError) as exc:
        return IssueResult("failed", error=f"«Мой налог» не настроен: {exc}"[:255])
    try:
        payload = _build_payload(service_name, amount_kopecks, operation_time)
    except ValueError as exc:
        return IssueResult("failed", error=f"данные чека не прошли проверку: {exc}"[:255])

    # ИНН нужен для ссылки на чек; получаем до создания чека, чтобы сбой здесь был безопасным.
    try:
        inn = await _get_inn(client)
    except UnauthorizedException as exc:
        return IssueResult("failed", error=_short(exc))
    except DomainException as exc:
        return IssueResult("retry", error=_short(exc))

    try:
        response = await client.http_client.post("/income", json_data=payload)
        data = response.json()
    except ConnectionException as exc:
        return IssueResult("retry", error=_short(exc))
    except NetworkException as exc:
        return IssueResult("unknown", error=_short(exc))
    except (UnauthorizedException, ValidationException, UnprocessableEntityException,
            ForbiddenException, NotFoundException, ClientException,
            RateLimitException) as exc:
        return IssueResult("failed", error=_short(exc))
    except ServerException as exc:
        return IssueResult("unknown", error=_short(exc))
    except DomainException as exc:
        return IssueResult("unknown", error=_short(exc))
    except ValueError as exc:
        return IssueResult("unknown", error=f"ответ не разобран: {exc}"[:255])

    receipt_uuid = data.get("approvedReceiptUuid") if isinstance(data, dict) else None
    if not receipt_uuid:
        return IssueResult("unknown", error="ответ ФНС без approvedReceiptUuid")
    url = RECEIPT_URL_TEMPLATE.format(inn=inn, uuid=receipt_uuid) if inn else None
    return IssueResult("sent", receipt_uuid=str(receipt_uuid), receipt_url=url)


async def _check_token() -> tuple[str, str | None]:
    """Вернуть (результат, подробность): ok / rejected (ФНС отказала, нужен новый вход) /
    unavailable (сеть или сбой ФНС: токен нерабочим не считается)."""
    try:
        client = _get_client()
    except (OSError, RuntimeError) as exc:
        return "rejected", f"состояние входа не настроено: {exc}"[:255]
    try:
        await client.user().get()
    except UnauthorizedException as exc:
        return "rejected", _short(exc)
    except DomainException as exc:
        return "unavailable", _short(exc)
    return "ok", None


def _seconds_until_next_check(now: dt.datetime) -> float:
    target = now.replace(hour=CHECK_HOUR_MSK, minute=0, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return (target - now).total_seconds()


async def _notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            logger.exception("не удалось отправить сообщение admin_id=%s", admin_id)


async def _check_with_retries() -> tuple[str, str | None]:
    result, detail = "unavailable", None
    for attempt in range(UNAVAILABLE_ATTEMPTS):
        result, detail = await check_token()
        if result != "unavailable":
            break
        if attempt + 1 < UNAVAILABLE_ATTEMPTS:
            await asyncio.sleep(UNAVAILABLE_PAUSE_SEC)
    return result, detail


async def _apply_check(bot: Bot, result: str, detail: str | None) -> None:
    global _token_state
    previous = _token_state
    _token_state = result
    logger.info("проверка токена «Мой налог»: %s (было: %s)", result, previous)
    if result == previous:
        return
    if result == "rejected":
        await _notify_admins(
            bot,
            "⚠️ Токен «Мой налог» нерабочий: ФНС отказала. Выпуск чеков не работает. "
            f"Нужен повторный вход (scripts/nalog_login.py на Panel). Причина: {detail}",
        )
    elif result == "unavailable":
        await _notify_admins(
            bot,
            f"⚠️ Не удалось проверить токен «Мой налог»: {UNAVAILABLE_ATTEMPTS} попытки "
            f"неудачны (сеть или сбой ФНС). Состояние токена неизвестно. Причина: {detail}",
        )
    elif result == "ok" and previous in ("rejected", "unavailable"):
        await _notify_admins(bot, "✅ Токен «Мой налог» снова рабочий.")


async def token_monitor_loop(bot: Bot) -> None:
    if not nalog_enabled():
        logger.info("«Мой налог» не настроен (NALOG_STATE_DIR) - проверка токена отключена")
        return
    await asyncio.sleep(FIRST_CHECK_DELAY_SEC)
    while True:
        try:
            result, detail = await _check_with_retries()
            await _apply_check(bot, result, detail)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("проверка токена «Мой налог»: сбой цикла")
        await asyncio.sleep(_seconds_until_next_check(dt.datetime.now(_MSK)))


_api_lock = asyncio.Lock()


async def issue_receipt(service_name: str, amount_kopecks: int,
                        operation_time: dt.datetime) -> IssueResult:
    """Запросы к ФНС идут по одному: refresh-токен ротируется при каждом обновлении,
    параллельное обновление из двух задач испортило бы сессию."""
    async with _api_lock:
        return await _issue_receipt(service_name, amount_kopecks, operation_time)


async def check_token() -> tuple[str, str | None]:
    async with _api_lock:
        return await _check_token()
