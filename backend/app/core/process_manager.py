"""
Process manager — fixed version.

Fixes:
- C2: Kill processes by PID (not by image name). This prevents accidentally
  killing other users' gallery-dl / yt-dlp processes on the same machine.
- Async wrapper around subprocess for non-blocking I/O.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProcessResult:
    return_code: int | None
    lines: list[str]


def resolve_gallery_dl_executable() -> list[str]:
    """Locate gallery-dl — prefer system install, fall back to python -m."""
    import shutil

    found = shutil.which("gallery-dl")
    if found:
        return [found]
    return [sys.executable, "-m", "gallery_dl"]


def resolve_ytdlp_executable() -> list[str]:
    """Locate yt-dlp — prefer system install, fall back to python -m."""
    import shutil

    found = shutil.which("yt-dlp")
    if found:
        return [found]
    return [sys.executable, "-m", "yt_dlp"]


def _get_hidden_startupinfo() -> subprocess.STARTUPINFO | None:
    if os.name != "nt":
        return None
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = subprocess.SW_HIDE
    return info


class AsyncProcessRunner:
    """
    Wraps subprocess.Popen for safe async streaming. Tracks PID so
    we can kill ONLY our own process (not all gallery-dl on the system).
    """

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._pid: int | None = None

    @property
    def pid(self) -> int | None:
        return self._pid

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(
        self,
        cmd: Sequence[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> asyncio.subprocess.Process:
        await self.stop()

        safe_cmd = [str(part) for part in cmd]

        self._process = await asyncio.create_subprocess_exec(
            *safe_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
            env=env,
        )
        self._pid = self._process.pid
        logger.info("→ gallery-dl started (PID %s)", self._pid)
        return self._process

    async def stream_output(self) -> AsyncIterator[str]:
        """Yield stdout lines as they arrive."""
        if self._process is None or self._process.stdout is None:
            return
        async for raw_line in self._process.stdout:
            try:
                line = raw_line.decode("utf-8", errors="ignore").rstrip("\n")
            except Exception:
                continue
            yield line

    async def wait(self) -> int:
        if self._process is None:
            return -1
        return await self._process.wait()

    async def stop(self, *, grace_seconds: float = 3.0) -> None:
        """
        Soft-then-hard kill. Only kills our tracked PID — never by image name.
        """
        if self._process is None:
            return

        try:
            if self._process.returncode is None:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=grace_seconds)
                except asyncio.TimeoutError:
                    logger.warning("Process %s did not exit gracefully, killing", self._pid)
                    self._process.kill()
                    await self._process.wait()
        except ProcessLookupError:
            pass
        except Exception:
            logger.exception("Error during process stop")
        finally:
            self._process = None
            self._pid = None

    def _redact_cmd(self, cmd: Sequence[str]) -> str:
        redacted: list[str] = []
        skip_next = False
        for idx, part in enumerate(cmd):
            if skip_next:
                skip_next = False
                continue
            if part in {"--cookies", "--download-archive", "--destination"} and idx + 1 < len(cmd):
                redacted.extend([part, "<redacted>"])
                skip_next = True
            else:
                redacted.append(part)
        return " ".join(redacted)
