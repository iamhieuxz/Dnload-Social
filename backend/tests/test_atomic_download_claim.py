import asyncio

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.downloads import run_pending
from app.database import Base
from app.models import Download, DownloadStatus, Platform, SourceType
from app.api.downloads import list_downloads


def test_run_pending_claims_rows_once(monkeypatch) -> None:
    async def run() -> None:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as seed:
            seed.add(Download(
                platform=Platform.INSTAGRAM,
                source_type=SourceType.LINK,
                url="https://instagram.com/p/example/",
                status=DownloadStatus.PENDING,
            ))
            await seed.commit()

        scheduled: list[int] = []
        async def enqueue(job_id: int) -> None:
            scheduled.append(job_id)

        from app.services.job_runner import job_runner
        monkeypatch.setattr(job_runner, "enqueue", enqueue)
        async with sessions() as session:
            bt1 = BackgroundTasks()
            first = await run_pending("instagram", db=session, background_tasks=bt1)
            # BackgroundTasks only run inside the FastAPI request lifecycle;
            # when calling the endpoint function directly we have to drain
            # the queue ourselves to fire the enqueue call.
            for task in bt1.tasks:
                if task.is_async:
                    await task.func(*task.args, **task.kwargs)
                else:
                    task.func(*task.args, **task.kwargs)
        async with sessions() as session:
            bt2 = BackgroundTasks()
            second = await run_pending("instagram", db=session, background_tasks=bt2)
            for task in bt2.tasks:
                if task.is_async:
                    await task.func(*task.args, **task.kwargs)
                else:
                    task.func(*task.args, **task.kwargs)

        assert first["marked"] == 1
        assert second["marked"] == 0
        assert second["job_id"] is None
        assert scheduled == [first["job_id"]]
        await engine.dispose()

    asyncio.run(run())


def test_list_downloads_query_maps_content_type() -> None:
    async def run() -> None:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            session.add(Download(
                platform=Platform.INSTAGRAM,
                source_type=SourceType.LINK,
                url="https://instagram.com/p/example/",
                content_type="post",
                status=DownloadStatus.PENDING,
            ))
            await session.commit()
        async with sessions() as session:
            result = await list_downloads(
                page=1,
                page_size=20,
                platform=None,
                status=None,
                source_type=None,
                search=None,
                job_id=None,
                db=session,
            )
        assert result.total == 1
        assert result.items[0].content_type == "post"
        await engine.dispose()

    asyncio.run(run())
