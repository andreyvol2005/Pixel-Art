from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)

from .config import DATABASE_URL

# pool_pre_ping: после перезапуска Postgres в пуле остаются мёртвые соединения,
# и без этой проверки приложение отдаёт ошибки вместо нормальных ответов.
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_schema() -> None:
    """Создаёт таблицы, если их ещё нет.

    Схема живёт в app/models.py и подтверждается этим вызовом на старте.
    Alembic здесь не нужен: единственная таблица pixels не меняет форму жизни
    после первого коммита. Если появится вторая-третья таблица — пора добавлять
    миграции (alembic revision --autogenerate).
    """
    from .models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("SELECT 1"))  # первое соединение открываем здесь