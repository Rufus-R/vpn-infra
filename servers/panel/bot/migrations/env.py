"""Окружение Alembic для бота. БД берётся из app.config (DB_PATH); для проверок на копии
БД достаточно передать DB_PATH в окружении (значение из .env не перезаписывает его)."""
from alembic import context
from sqlalchemy import create_engine, pool

from app.config import DB_PATH
from app.db.base import Base
import app.db.models  # noqa: F401  (регистрирует таблицы в Base.metadata)

target_metadata = Base.metadata
URL = f"sqlite:///{DB_PATH}"


def run_migrations_offline() -> None:
    context.configure(url=URL, target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(URL, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
