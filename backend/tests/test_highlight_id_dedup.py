"""Regression test: from-highlight-ids skips IDs that already exist in
the downloads table (idempotent re-paste of the same reel ID list).

Bug B-08 from docs/BUGS.md.
"""
from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.downloads import from_highlight_ids
from app.database import Base
from app.models import Download, DownloadStatus, Platform, SourceType


def test_highlight_ids_dedup_against_existing_rows(monkeypatch) -> None:
    async def run() -> None:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        # Pre-seed one of the IDs as an existing row.
        from app.api.downloads import FromHighlightIdsRequest
        async with sessions() as session:
            existing = FromHighlightIdsRequest(
                user="annykim__",
                ids=["123456789012345"],
            )
            first = await from_highlight_ids(existing, db=session)
            assert first.created == 1
            assert first.skipped == 0

        # Re-paste the same list plus one new ID. Existing URL must
        # be counted as skipped, not re-inserted.
        async with sessions() as session:
            second = FromHighlightIdsRequest(
                user="annykim__",
                ids=["123456789012345", "987654321098765"],
            )
            result = await from_highlight_ids(second, db=session)
            assert result.created == 1, "only the new ID should be created"
            assert result.skipped == 1, "the existing ID should be skipped"

        await engine.dispose()

    asyncio.run(run())
