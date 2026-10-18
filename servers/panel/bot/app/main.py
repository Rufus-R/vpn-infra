import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from app.config import BOT_TOKEN, TG_PROXY_URL
from app.db.base import init_db
from app.db.seed import seed_defaults
from app.handlers import router
from app.payments import payments_enabled, reconcile_loop
from app.webhook import start_webhook

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

dp = Dispatcher()
dp.include_router(router)


async def main() -> None:
    await init_db()  # применяет миграции Alembic (upgrade head)
    await seed_defaults()
    session = AiohttpSession(proxy=TG_PROXY_URL) if TG_PROXY_URL else AiohttpSession()
    bot = Bot(token=BOT_TOKEN, session=session)

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
        if reconcile_task is not None:
            reconcile_task.cancel()
        if runner is not None:
            await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
