import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from app.config import BOT_TOKEN, TG_PROXY_URL
from app.db.base import init_db
from app.db.seed import seed_defaults
from app.handlers import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

dp = Dispatcher()
dp.include_router(router)


async def main() -> None:
    await init_db()  # TODO: заменить на Alembic-миграции перед продакшн-запуском
    await seed_defaults()
    session = AiohttpSession(proxy=TG_PROXY_URL) if TG_PROXY_URL else AiohttpSession()
    bot = Bot(token=BOT_TOKEN, session=session)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
