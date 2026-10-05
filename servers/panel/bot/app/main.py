import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy import select

from app.config import BOT_TOKEN, TG_PROXY_URL
from app.db.base import init_db, async_session
from app.db.models import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    # TODO: вынести в app/services/users.py по мере роста кода; обработать deep-link ref_<id>
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(tg_id=message.from_user.id, username=message.from_user.username)
            session.add(user)
            await session.commit()
    await message.answer(
        "Добро пожаловать! (черновик — меню тарифов/триала/подписок будет добавлено)"
    )


async def main() -> None:
    await init_db()  # TODO: заменить на Alembic-миграции перед продакшн-запуском
    session = AiohttpSession(proxy=TG_PROXY_URL) if TG_PROXY_URL else AiohttpSession()
    bot = Bot(token=BOT_TOKEN, session=session)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
