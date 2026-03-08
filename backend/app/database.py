from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from sqlmodel import SQLModel

from .config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    future=True,
    pool_pre_ping=True,
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        await conn.execute(text("ALTER TABLE buildings ADD COLUMN IF NOT EXISTS servicing_org_name VARCHAR"))
        await conn.execute(text("ALTER TABLE buildings ADD COLUMN IF NOT EXISTS servicing_org_phone VARCHAR(100)"))
        await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS postponed_reason VARCHAR"))
        await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS postponed_at TIMESTAMP"))
        await conn.execute(text("ALTER TABLE subscriber_requests ADD COLUMN IF NOT EXISTS postponed_reason VARCHAR"))
        await conn.execute(text("ALTER TABLE subscriber_requests ADD COLUMN IF NOT EXISTS postponed_at TIMESTAMP"))

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
