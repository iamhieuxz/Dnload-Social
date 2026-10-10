"""Smoke test: chạy pipeline của project với cookie rỗng để verify
- URL `/highlights` được truyền đúng xuống gallery-dl
- gallery-dl nhận đúng InstagramHighlightsExtractor
- pipeline (URL → process → log parsing) hoạt động tới bước IG từ chối cookie

Kỳ vọng: IG trả 401/login required, KHÔNG tải được file.
Đây là test pipeline, không phải test tải thật.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from process_manager import ProcessManager
from downloader import Downloader
from rate_limit import RateLimitGuard
from models import AppConfig, RuntimeState
from services import InstagramService

empty_cookie = ROOT / "backend" / "_empty_cookie.txt"
tmp_dest = tempfile.mkdtemp(prefix="hl_smoke_")
print(f"[setup] dest={tmp_dest}")
print(f"[setup] cookie={empty_cookie} (exists={empty_cookie.exists()})")

cfg = AppConfig(
    download_folder=tmp_dest,
    cookie_path=str(empty_cookie),
    backup_cookie_path=str(empty_cookie),
    list_txt_path=str(ROOT / "backend" / "requirements.txt"),  # tạm, không dùng
)
state = RuntimeState()
pm = ProcessManager()
downloader = Downloader(pm)
guard = RateLimitGuard()
svc = InstagramService(downloader, guard, cfg, state)

print("\n[run] update_single include_highlights=True (URL: /annykim__/highlights/)")
print("=" * 60)
try:
    svc.update_single("annykim__", disable_range=True,
                      include_posts=False, include_stories=False,
                      include_highlights=True)
except Exception as e:
    print(f"[run] exception: {type(e).__name__}: {e}")
print("=" * 60)

# Check what landed on disk
files = list(Path(tmp_dest).rglob("*"))
print(f"\n[result] files in dest: {len([f for f in files if f.is_file()])}")
for f in files:
    if f.is_file():
        print(f"  - {f.relative_to(tmp_dest)}  ({f.stat().st_size} bytes)")
