from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import DB_PATH


class Base(DeclarativeBase):
    pass


engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Создать таблицы, если их нет. На проде использовать Alembic-миграции, не эту функцию."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
