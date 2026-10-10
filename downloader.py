from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

from process_manager import ProcessManager


def resolve_gallery_dl_executable() -> list[str]:
    found = shutil.which('gallery-dl')
    if found:
        return [found]
    return [sys.executable, '-m', 'gallery_dl']


@dataclass(frozen=True, slots=True)
class GalleryDlTuning:
    sleep_request: str = '10-24'
    sleep: str = '5-12'
    retries: int = 8
    retry_sleep: str = '60-180'
    request_timeout: int = 60


class Downloader:
    def __init__(self, process_manager: ProcessManager, tuning: GalleryDlTuning | None = None) -> None:
        self.pm = process_manager
        self.tuning = tuning or GalleryDlTuning()

    def build_gallery_dl_command(
        self,
        url: str,
        destination: str,
        cookie_file: str,
        limit_range: str | None = None,
        disable_range: bool = False,
        prefix: str = "", # [THÊM MỚI] Biến cấu hình Tiền tố
    ) -> list[str]:
        dest_path = Path(destination).expanduser()
        
        # [CẤU HÌNH MỚI] Nội suy tiền tố vào trước ngày tháng
        filename_template = f'{prefix}{{date:%Y-%m-%d}}_{{shortcode|id}}_{{num:04}}.{{extension}}'
        
        cmd: list[str] = [
            *resolve_gallery_dl_executable(),
            url,
            '--destination', str(dest_path),
            '--sleep-request', self.tuning.sleep_request,
            '--sleep', self.tuning.sleep,
            '--retries', str(self.tuning.retries),
            '--http-timeout', str(self.tuning.request_timeout),
            '-o', 'cache.file=none',
            '-o', 'directory=["."]',
            '-o', f'filename={filename_template}'
        ]
        
        cmd.extend(["--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"])
        
        if cookie_file and os.path.exists(cookie_file):
            cmd.extend(["--cookies", os.path.normpath(cookie_file)])

        archive_path = dest_path / '.instagram_download_archive.sqlite'
        cmd.extend(['--download-archive', str(archive_path), '--abort', '20'])

        if limit_range and not disable_range:
            cmd.extend(['--range', limit_range])
        return cmd

    def execute_download(
        self,
        url: str,
        destination: str,
        cookie_file: str,
        limit_range: str | None = None,
        disable_range: bool = False,
        prefix: str = "", # [THÊM MỚI]
    ) -> Generator[str, None, None]:
        
        temp_cookie_path = None
        if cookie_file:
            original_cookie = Path(cookie_file).expanduser()
            if original_cookie.exists():
                fd, temp_cookie_path = tempfile.mkstemp(suffix='.txt', prefix='ig_cookie_')
                os.close(fd)
                try:
                    shutil.copy2(original_cookie, temp_cookie_path)
                except Exception as e:
                    logging.warning('⚠️ Không thể tạo file cookie tạm: %s', e)
                    temp_cookie_path = None

        actual_cookie_file = temp_cookie_path if temp_cookie_path else cookie_file

        cmd = self.build_gallery_dl_command(url, destination, actual_cookie_file, limit_range, disable_range, prefix)
        proc = self.pm.start(cmd)

        captured: list[str] = []
        try:
            if proc.stdout is not None:
                for raw_line in proc.stdout:
                    line = raw_line.rstrip('\n')
                    captured.append(line)
                    yield line
                    logging.info('[DL] %s', line)

            return_code = proc.wait()
            if return_code not in (0, None):
                logging.warning('Engine tải xuống kết thúc với mã lỗi: %s', return_code)
                for line in captured:
                    lower = line.lower()
                    if any(token in lower for token in ('error', 'usage:', 'unrecognized', 'failed', 'exception')):
                        logging.warning('⚠️ [ENGINE] %s', line)
        finally:
            if temp_cookie_path and os.path.exists(temp_cookie_path):
                try:
                    os.remove(temp_cookie_path)
                except OSError:
                    pass