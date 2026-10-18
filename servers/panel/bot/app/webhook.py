"""Приём HTTP-уведомлений ЮKassa. См. docs/checkpoint-2026-10-17-payments.md, раздел 10.

aiohttp-сервер слушает только 127.0.0.1:WEBHOOK_PORT; снаружи его открывает nginx
(location с секретным путём, заголовок X-Real-IP = $remote_addr, access_log off).
Тело уведомления не подписано: проверяются секрет в пути и IP отправителя, а из тела берутся
только event и object.id — всё остальное решает GET платежа в process_payment_event.
Ответ — быстрый HTTP 200; ошибки обработки только логируются (повтор — за сверкой).
"""
from __future__ import annotations
import asyncio
import hmac
import ipaddress
import logging

from aiohttp import web
from aiogram import Bot

from app.config import WEBHOOK_PORT, YOOKASSA_WEBHOOK_SECRET
from app.payments import process_payment_event

logger = logging.getLogger("webhook")

# Адреса ЮKassa из официальной документации («Входящие уведомления»), прочитаны 18.10.2026.
_ALLOWED_NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    "185.71.76.0/27",
    "185.71.77.0/27",
    "77.75.153.0/25",
    "77.75.156.11/32",
    "77.75.156.35/32",
    "77.75.154.128/25",
    "2a02:5180::/32",
))
_HANDLED_EVENTS = {"payment.succeeded", "payment.canceled"}
_BOT_KEY = web.AppKey("bot", Bot)
_TASKS: set[asyncio.Task] = set()


def _is_yookassa_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError:
        return False
    return any(ip in network for network in _ALLOWED_NETWORKS)


async def _process(bot: Bot, provider_payment_id: str) -> None:
    try:
        await process_payment_event(bot, provider_payment_id)
    except Exception:
        logger.exception("webhook: ошибка обработки платежа %s", provider_payment_id)


async def _handle(request: web.Request) -> web.Response:
    secret = request.match_info["secret"]
    if not YOOKASSA_WEBHOOK_SECRET or not hmac.compare_digest(
        secret.encode(), YOOKASSA_WEBHOOK_SECRET.encode()
    ):
        return web.Response(status=404)
    if not _is_yookassa_ip(request.headers.get("X-Real-IP", "")):
        logger.warning("webhook: запрос с IP вне списка ЮKassa")
        return web.Response(status=403)
    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError):
        return web.Response(status=400)
    if not isinstance(body, dict):
        return web.Response(status=400)

    event = body.get("event")
    obj = body.get("object")
    provider_payment_id = obj.get("id") if isinstance(obj, dict) else None
    if event in _HANDLED_EVENTS and isinstance(provider_payment_id, str):
        task = asyncio.create_task(_process(request.app[_BOT_KEY], provider_payment_id))
        _TASKS.add(task)
        task.add_done_callback(_TASKS.discard)
    return web.Response(status=200, text="ok")


async def start_webhook(bot: Bot) -> web.AppRunner:
    app = web.Application(client_max_size=64 * 1024)
    app[_BOT_KEY] = bot
    app.router.add_post("/yookassa-webhook/{secret}/", _handle)
    # access_log=None: секретный путь не должен попадать в журнал.
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", WEBHOOK_PORT).start()
    logger.info("webhook ЮKassa слушает 127.0.0.1:%s", WEBHOOK_PORT)
    return runner
