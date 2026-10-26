import asyncio
import logging
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from app.broadcast import resume_broadcasts
from app.config import BOT_TOKEN, PANEL_API_BASE, TG_PROXY_URL
from app.db.base import init_db
from app.db.seed import seed_defaults
from app.handlers import router
from app.nalog import close_client, token_monitor_loop
from app.payments import payments_enabled, reconcile_loop
from app.reminders import reminder_loop
from app.webhook import start_webhook

logging.basicConfig(level=logging.INFO)


class _HidePanelPath(logging.Filter):
    """httpx на уровне INFO пишет полный URL запроса; к Panel он содержит секретный
    webBasePath. Записи с этим сегментом пути в журнал не пропускаем."""

    def __init__(self, secret: str) -> None:
        super().__init__()
        self._secret = secret

    def filter(self, record: logging.LogRecord) -> bool:
        return self._secret not in record.getMessage()


_panel_secret = urlparse(PANEL_API_BASE).path.rstrip("/").removesuffix("/panel/api")
if _panel_secret.strip("/"):
    logging.getLogger("httpx").addFilter(_HidePanelPath(_panel_secret))

logger = logging.getLogger("bot")

dp = Dispatcher()
dp.include_router(router)


async def main() -> None:
    await init_db()  # применяет миграции Alembic (upgrade head)
    await seed_defaults()
    session = AiohttpSession(proxy=TG_PROXY_URL) if TG_PROXY_URL else AiohttpSession()
    bot = Bot(token=BOT_TOKEN, session=session)
    resume_task = asyncio.create_task(resume_broadcasts(bot))
    reminder_task = asyncio.create_task(reminder_loop(bot))
    nalog_task = asyncio.create_task(token_monitor_loop(bot))

    runner = None
    reconcile_task = None
    if payments_enabled():
        runner = await start_webhook(bot)
        reconcile_task = asyncio.create_task(reconcile_loop(bot))
    else:
        logger.info("ЮKassa не настроена — приём платежей отключён")

    try:
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        nalog_task.cancel()
        if reconcile_task is not None:
            reconcile_task.cancel()
        if runner is not None:
            await runner.cleanup()
        await close_client()


if __name__ == "__main__":
    asyncio.run(main())
