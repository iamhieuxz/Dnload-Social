from __future__ import annotations

import ctypes
import os
import sys
import glob
import tempfile
from pathlib import Path


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def request_admin_privileges() -> None:
    if is_admin():
        return
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
    sys.exit()


def clean_username(raw_input: str) -> str:
    if not raw_input:
        return ""
    s = raw_input.strip().replace('"', '')
    s = s.replace("https://instagram.com/", "").replace("https://www.instagram.com/", "")
    if "/" in s:
        s = s.split("/")[0]
    if "?" in s:
        s = s.split("?")[0]
    return s.strip()


def count_local_files(folder_path: str) -> int:
    path = Path(folder_path)
    if not path.exists():
        return 0
    return sum(1 for entry in path.rglob("*") if entry.is_file())


def cleanup_temp_cookies() -> None:
    """[CẢI TIẾN] Dọn dẹp các file cookie tạm bị sót lại do ứng dụng crash từ các phiên trước."""
    temp_dir = tempfile.gettempdir()
    pattern = os.path.join(temp_dir, 'ig_cookie_*.txt')
    count = 0
    for f in glob.glob(pattern):
        try:
            os.remove(f)
            count += 1
        except Exception:
            pass
    if count > 0:
        print(f"[CLEANUP] Đã dọn dẹp {count} file cookie tạm (rác) từ phiên làm việc trước.")