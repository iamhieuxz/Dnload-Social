"""Regression test: pending-summary now exposes `failed` count.

Bug B-31 from docs/BUGS.md.
"""
from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.downloads import pending_summary
from app.database import Base
from app.models import Download, DownloadStatus, Platform, SourceType


def test_pending_summary_includes_failed_count() -> None:
    async def run() -> None:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as s:
            for i, status in enumerate([
                DownloadStatus.PENDING,
                DownloadStatus.PENDING,
                DownloadStatus.DOWNLOADING,
                DownloadStatus.FAILED,
                DownloadStatus.FAILED,
                DownloadStatus.FAILED,
                DownloadStatus.COMPLETED,  # not counted
            ]):
                s.add(Download(
                    platform=Platform.INSTAGRAM,
                    source_type=SourceType.LINK,
                    url=f"https://instagram.com/p/{i}/",
                    status=status,
                ))
            await s.commit()
        async with sessions() as s:
            res = await pending_summary(platform="instagram", db=s)
        assert res["pending"] == 2
        assert res["in_flight"] == 1
        assert res["failed"] == 3
        assert res["resumable"] == 3  # 2 pending + 1 in_flight
        await engine.dispose()

    asyncio.run(run())
