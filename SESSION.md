# Session Summary — web-app2

> File này được agent tự động cập nhật mỗi lần làm việc xong.
> Đọc file này để hiểu nhanh dự án thay vì đọc lại toàn bộ code.

---

## Tổng quan

**web-app2** là web app local để quản lý download media từ **Instagram** và **Twitter / X**.
Giao diện web (Next.js) + backend API (FastAPI) + database (SQLite mặc định, PostgreSQL tùy chọn).

```
f:\web-app2\
├── backend/              # FastAPI
│   ├── app/
│   │   ├── main.py          # Entry point, CORS, router registration
│   │   ├── config.py        # Settings (từ .env, không còn hardcoded)
│   │   ├── database.py      # SQLAlchemy async + SQLite/PostgreSQL
│   │   ├── models/          # ORM: account, media, job, download, setting, rate_limit_event, twitter_cookie
│   │   ├── schemas/         # Pydantic schemas
│   │   ├── api/             # Routes: accounts, jobs, media, stats, settings, cookies, ws, gallery, downloads, logs
│   │   ├── services/
│   │   │   ├── instagram.py     # Instagram service (gallery-dl)
│   │   │   ├── twitter.py       # Twitter service (yt-dlp)
│   │   │   ├── job_runner.py    # Job executor — serialised, 1 job tại 1 thời điểm
│   │   │   └── media_scanner.py # Scan folder → index vào DB
│   │   └── core/
│   │       ├── process_manager.py   # Async subprocess (PID tracking)
│   │       ├── rate_limit.py         # Rate limit guard
│   │       ├── websocket_manager.py  # WS broadcast
│   │       └── logging_config.py     # In-memory log buffer + WS handler
│   ├── secrets/cookies/    # Cookie files (cookie1.txt, cookie2.txt; twitter/tw_cookie1.txt)
│   ├── data/               # SQLite DB: igdownloader.db
│   ├── migrations/         # Alembic migrations
│   ├── pyproject.toml
│   └── requirements.txt
├── frontend/              # Next.js 15 + shadcn/ui + TanStack Query
│   ├── app/
│   │   ├── layout.tsx         # Root layout: Sidebar + header + dark theme
│   │   ├── page.tsx           # Dashboard: console + active job + live terminal
│   │   ├── accounts/          # Accounts page (disk scan)
│   │   ├── gallery/           # File browser
│   │   ├── downloads/         # Download queue
│   │   ├── jobs/             # Job history
│   │   ├── media/            # Media browser
│   │   └── settings/         # Settings
│   ├── components/
│   │   ├── Sidebar.tsx
│   │   └── (shadcn components)
│   └── lib/
│       ├── api.ts            # Axios client + all TypeScript interfaces
│       └── websocket.ts      # WS client
├── docs/                   # Docs folder
├── logs/                   # Backend + frontend logs
├── .pids/                  # PID files (start/stop scripts)
├── config.py               # OLD: hardcoded config (legacy, không dùng nữa)
├── main.py                 # OLD: CLI entry (legacy)
├── gui.py                  # OLD: Tkinter GUI (legacy, đã bỏ)
├── services.py             # OLD: legacy service (không dùng nữa)
├── process_manager.py      # OLD: legacy process manager
├── rate_limit.py           # OLD: legacy rate limit
├── models.py               # OLD: legacy dataclass models
├── utils.py                # OLD: legacy utils
├── start.ps1 / start.bat / start.sh   # One-click launcher
├── stop.ps1 / stop.bat / stop.sh      # Stop all services
├── docker-compose.yml      # PostgreSQL + services
├── README.md               # Hướng dẫn tổng
└── README-RUN.md          # Hướng dẫn chạy nhanh (SQLite mode)
```

---

## Scripts

```
start.ps1   # One-click: kiểm tra env → backend → frontend → mở trình duyệt
stop.ps1    # Stop tất cả services + giải phóng port
```

Chạy: `.\start.ps1` → mở http://localhost:3000

---

## Database Schema (SQLite)

```sql
accounts        -- username, destination_folder, total_posts/stories/highlights, size
media           -- file records (path, shortcode, date, size, hash)
downloads       -- queue: url, platform, source, content_type, status (pending/downloading/completed/failed)
jobs            -- lịch sử chạy: type, targets (JSON), status, new_files_count, total_processed
rate_limit_events  -- log khi bị rate limit
settings        -- key-value config (thay hardcoded config.py)
twitter_cookies -- metadata về cookie files
```

---

## API Endpoints quan trọng

```
GET  /api/health
POST /api/downloads/batch           -- Tạo nhiều download row
POST /api/downloads/run-pending       -- Chạy all pending của 1 platform
GET  /api/downloads/pending-summary  -- Số pending/in_flight/resumable
GET  /api/downloads                  -- List + filter queue
GET  /api/downloads/stats            -- Tổng hợp stats
POST /api/downloads/{id}/retry      -- Retry failed/skipped

GET  /api/jobs/active               -- Job đang chạy (polling)
GET  /api/jobs/{id}/logs            -- Log của job
POST /api/jobs/{id}/stop            -- Dừng job

GET  /api/accounts/scan-from-disk    -- Scan folder → account list (disk, không query DB)

WS   /ws                            -- WebSocket: nhận log realtime + job_update + download_update
```

---

## Bug đã fix (từ code review 8/10)

| ID | Mô tả | File |
|----|--------|------|
| C1 | Race condition submit job → giờ dùng asyncio.Lock, chỉ 1 job chạy | `job_runner.py` |
| C2 | `force_kill_engines` kill toàn bộ process trên máy → giờ kill by PID | `process_manager.py` |
| C3 | Hardcoded `E:\gallery-dl` → giờ từ `.env` / Settings | `config.py` |
| C4 | `count_local_files` rglob mỗi lần → giờ dùng cached counts trong DB | `media_scanner.py` |
| C5 | Cookie fallback yield hết rồi mới detect rate limit → giờ abort ngay | `instagram.py` |
| C6 | Cache không reset khi đổi cookie | `downloads.py` (clear cache khi đổi cookie) |

---

## UI Pages

| Route | Chức năng |
|-------|-----------|
| `/` | Dashboard: console nhập URL + live terminal |
| `/accounts` | Danh sách account folders (scan từ disk) |
| `/gallery` | File browser + search |
| `/downloads` | Download queue table |
| `/jobs` | Lịch sử jobs |
| `/media` | Media browser |
| `/settings` | Settings |

---

## Config quan trọng

```
DOWNLOAD_FOLDER=E:/gallery-dl/instagram
TWITTER_DOWNLOAD_FOLDER=E:/gallery-dl/twitter
COOKIE_FOLDER=./secrets/cookies
DATABASE_URL=sqlite+aiosqlite:///./data/igdownloader.db
  # Đổi thành postgresql+asyncpg://... nếu dùng PostgreSQL
RATE_LIMIT_MIN_DELAY=18
RATE_LIMIT_MAX_DELAY=45
RATE_LIMIT_BATCH_SIZE=8
```

---

## Cookie files

- Instagram: `secrets/cookies/cookie1.txt`, `cookie2.txt`
- Twitter: `secrets/cookies/twitter/tw_cookie1.txt`, `tw_cookie2.txt`

Upload cookie qua UI: Settings → Cookies tab (Instagram) hoặc Settings → Twitter tab.

---

## Layer routing (Instagram)

`content_type` column trong bảng `downloads` quyết định layer nào chạy:

| content_type | URL pattern | Layer | Test result |
|---|---|---|---|
| `post` | `instagram.com/<user>/` (timeline) | Layer 1 | OK |
| `story` | `instagram.com/stories/<user>/` (24h) | Layer 2 | OK |
| `highlight` | `instagram.com/<user>/highlights/` | Layer 3 | **OK — 497 files trong 110s** với user `annykim__` |

URL highlight `https://www.instagram.com/<user>/highlights/` được gallery-dl 1.32.16 detect đúng thành `InstagramHighlightsExtractor`. Pipeline flow:

```
UI gửi content_type=highlight
  → job_runner._process_one() 
  → service.download(content_type="highlight")
  → service.add_highlights(target) 
  → URL: "https://www.instagram.com/annykim__/highlights/"
  → gallery-dl chạy với prefix "HL_"
```

---

## Known quirks / TODO

- [ ] `cookie_encryption_key` — mã hóa cookie file khi lưu (chưa implement)
- [ ] `highlight` URL detection có thể bị bypass bởi IG URL thay đổi
- [ ] `_test_highlight_pipeline.py` và `_test_highlight_url.py` là test files trong backend/
- [ ] `fix_orphaned_jobs.py` là script dọn dẹp job bị treo

---

*Cập nhật: 2026-10-10 bởi Cursor Agent*
