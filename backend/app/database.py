"""
Async SQLAlchemy engine + session factory.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()

_IS_SQLITE = _settings.database_url.startswith("sqlite")

# SQLite async (via aiosqlite) doesn't support pool_pre_ping; skip it for SQLite.
_engine_kwargs: dict = {"echo": False}
if _IS_SQLITE:
    # Two jobs now write per row (one per platform), and `connect_args`
    # timeout is what turns a momentary "database is locked" into a short
    # wait instead of a failed download row.
    _engine_kwargs["connect_args"] = {"timeout": 30.0}
else:
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20
    _engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(_settings.database_url, **_engine_kwargs)

if _IS_SQLITE:
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        """WAL lets readers (the UI polling /api/jobs) run alongside the
        writers; without it a single write lock blocks every poll."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
        finally:
            cursor.close()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Use this in background tasks (not in request handlers)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
