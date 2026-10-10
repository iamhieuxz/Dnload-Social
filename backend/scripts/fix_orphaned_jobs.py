"""
Cleanup helper for stuck/orphaned Jobs.

Run as:
    $env:PYTHONPATH = "F:\\web-app2\\backend"
    .venv\\Scripts\\python.exe scripts/fix_orphaned_jobs.py

Marks every QUEUED / RUNNING job as STOPPED so the UI doesn't show a
zombie job forever. Also resets any DOWNLOADING rows back to PENDING
so the next run-pending call can re-pick them up — this is the
"perfect resume" guarantee when the user restarts the app after a
crash.
"""
import asyncio

from app.database import session_scope
from app.models import Download, DownloadStatus, Job, JobStatus
from sqlalchemy import update as _update
from datetime import datetime


async def main() -> None:
    async with session_scope() as session:
        # 1. Reset every DOWNLOADING row to PENDING (the JobRunner has its
        # own startup sweep, but we do it here too in case the user
        # invokes this script BEFORE the runner starts up).
        r1 = await session.execute(
            _update(Download)
            .where(Download.status == DownloadStatus.DOWNLOADING)
            .values(status=DownloadStatus.PENDING)
        )
        # 2. Mark every QUEUED / RUNNING job as STOPPED. Leave COMPLETED,
        # FAILED and STOPPED untouched.
        r2 = await session.execute(
            _update(Job)
            .where(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
            .values(
                status=JobStatus.STOPPED,
                error_message="Orphaned job — manually cleaned up",
                finished_at=datetime.utcnow(),
            )
        )
        print(f"Reset {r1.rowcount} stuck download(s) to PENDING")
        print(f"Marked {r2.rowcount} stuck job(s) as STOPPED")


if __name__ == "__main__":
    asyncio.run(main())
