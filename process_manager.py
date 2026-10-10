from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from threading import Thread
from typing import Sequence


@dataclass(slots=True)
class ProcessResult:
    return_code: int | None


class ProcessManager:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self._stream_thread: Thread | None = None

    def get_hidden_startupinfo(self) -> subprocess.STARTUPINFO | None:
        if os.name != 'nt':
            return None
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        return startupinfo

    def start(self, cmd: Sequence[str]) -> subprocess.Popen[str]:
        self.stop()
        safe_cmd = [str(part) for part in cmd]
        logging.info("Khởi chạy tiến trình hệ thống: %s", self._redact_cmd(safe_cmd))
        self.process = subprocess.Popen(
            safe_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            startupinfo=self.get_hidden_startupinfo(),
            errors='ignore',
            bufsize=1,
        )
        self._stream_thread = None
        return self.process

    def _redact_cmd(self, cmd: Sequence[str]) -> str:
        redacted: list[str] = []
        skip_next = False
        for idx, part in enumerate(cmd):
            if skip_next:
                skip_next = False
                continue
            if part in {'--cookies', '--download-archive', '--destination'} and idx + 1 < len(cmd):
                redacted.extend([part, '<redacted>'])
                skip_next = True
            else:
                redacted.append(part)
        return ' '.join(redacted)

    def force_kill_engines(self) -> None:
        if os.name != 'nt':
            return
        try:
            hidden_info = self.get_hidden_startupinfo()
            for image in ('gallery-dl.exe', 'yt-dlp.exe'):
                # [CẢI TIẾN] Chỉ diệt nếu tiến trình thực sự còn treo sau khi đóng mềm
                check = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {image}'], capture_output=True, text=True, startupinfo=hidden_info)
                if image in check.stdout:
                    subprocess.run(
                        ['taskkill', '/f', '/im', image],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        startupinfo=hidden_info,
                        check=False,
                    )
        except Exception:
            logging.exception('Không thể tắt cưỡng chế engine')

    def stop(self) -> None:
        if self.process is not None:
            try:
                self.process.terminate() # [CẢI TIẾN] Gửi tín hiệu đóng mềm
                self.process.wait(timeout=3) # [CẢI TIẾN] Chờ 3 giây để SQLite lưu dữ liệu an toàn
            except Exception:
                logging.warning('Tiến trình không phản hồi đóng mềm, chuẩn bị cưỡng chế tắt...')
            finally:
                self.process = None
        self.force_kill_engines()

    def read_output_lines(self) -> list[str]:
        if self.process is None or self.process.stdout is None:
            return []
        lines: list[str] = []
        try:
            for raw_line in self.process.stdout:
                line = raw_line.rstrip('\n')
                lines.append(line)
                logging.info('[ENGINE] %s', line)
        except Exception:
            logging.exception('Lỗi khi đọc output của tiến trình')
        return lines