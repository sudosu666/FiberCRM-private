from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from sqlmodel import SQLModel

from .config import settings
from . import models  # noqa: F401  # Ensure SQLModel metadata includes all tables.

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
        columns_to_add = [
            ("buildings", "servicing_org_name", "VARCHAR"),
            ("buildings", "servicing_org_phone", "VARCHAR(100)"),
            ("tasks", "postponed_reason", "VARCHAR"),
            ("tasks", "postponed_at", "TIMESTAMP"),
            ("subscriber_requests", "postponed_reason", "VARCHAR"),
            ("subscriber_requests", "postponed_at", "TIMESTAMP"),
        ]
        if conn.dialect.name == "postgresql":
            for table, column, dtype in columns_to_add:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {dtype}"))

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
