import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import DB_PATH

BOT_ROOT = Path(__file__).resolve().parents[2]


class Base(DeclarativeBase):
    pass


engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _upgrade_to_head() -> None:
    cfg = Config(str(BOT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BOT_ROOT / "migrations"))
    command.upgrade(cfg, "head")


async def init_db() -> None:
    """Привести схему БД к актуальной ревизии Alembic (upgrade head).
    Для БД, созданной до Alembic, один раз вручную выполнить `alembic stamp 0001`:
    иначе upgrade упадёт на уже существующих таблицах."""
    await asyncio.to_thread(_upgrade_to_head)
