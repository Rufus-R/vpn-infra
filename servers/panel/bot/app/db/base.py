from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import DB_PATH


class Base(DeclarativeBase):
    pass


engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Создать таблицы, если их нет, и применить аддитивные dev-миграции.
    На проде использовать Alembic-миграции, не эту функцию (TODO, см. bot.md, B11 п.6)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _add_missing_columns(conn, "plans", {"description": "VARCHAR(255)"})


async def _add_missing_columns(conn, table: str, columns: dict[str, str]) -> None:
    """Идемпотентно добавляет отсутствующие колонки через ALTER TABLE ADD COLUMN.
    Временное решение до подключения Alembic (09.10.2026, раздел "Тарифы") — безопасно
    для SQLite: аддитивно, не трогает существующие строки/колонки."""
    result = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
    existing = {row[1] for row in result.fetchall()}
    for col_name, col_type in columns.items():
        if col_name not in existing:
            await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
