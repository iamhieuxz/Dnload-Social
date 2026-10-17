# Session Summary — web-app2

> File này được agent tự đọc để hiểu nhanh dự án thay vì đọc lại toàn bộ code.

## Bug fix — Run pending stuck — 2026-10-15 14:05

User bấm "Run pending" trên UI → log không chạy, file không tải. Root cause 3 lớp:

1. `backend/.env` thiếu `COOKIE_ENCRYPTION_KEY` (key trống) → `_load_cookie_paths` raise 503.
2. `JobRunner._run` không có try/except quanh `_execute` → exception bay ra, job kẹt RUNNING vĩnh viễn trong DB. Đây là root bug lớn nhất: dù user upload cookie đúng, bất kỳ exception nào (cookie key, DB down, OOM, ...) đều làm job kẹt.
3. `_run` finally gọi `clear_job_logs` ngay cả khi job vừa fail → log bị xoá trước khi UI kịp xem.

Fix: thêm try/except + `_mark_job_failed` mới + tách `clear_job_logs` ra chỉ chạy khi COMPLETED/STOPPED. Generate Fernet key, thêm vào `.env`. Bonus: normalize tzinfo trong `/api/downloads/stats` (cũng bị 500).

Tham khảo: `docs/BUGS.md` mục `job-stuck-running-on-exception` (Resolved). Test mới `test_run_marks_job_failed.py` PASS. Full pytest 10/10. Job 78/79 (post-fix) COMPLETED bình thường, 0 new_files vì user chưa upload cookie thật vào slot.

## Bug sweep round 2 — 2026-10-15 13:45

Theo `docs/BUGS.md`, đợt này sửa 9 mục Open (xem `Resolved` section):

- `datetime-utcnow-deprecated`: 17 occurrence `datetime.utcnow()` → `datetime.now(timezone.utc)` ở 6 file backend.
- `safe-path-strict`: chuẩn hoá `_safe_path`, chặn drive-relative `C:foo`.
- `settings-patch-noop`: PATCH /api/settings → 501 thay vì echo.
- `filetime-heuristic`: bỏ heuristic 2286, tin Python đã normalize.
- `delete-media-orphan`: đổi thứ tự xoá file trước DB.
- `classify-duplicated`: tạo `app/core/media_types.py`, dùng chung cho gallery + accounts.
- `sidebar-poll-wasteful`: refetchInterval dynamic.
- `runner-global-stale-reset`: enqueue sweep 1 lần + filter `job_id != current`.
- `ytdlp-not-declared`: thêm `yt-dlp>=2024.10.7` vào requirements.

Verification: pytest 9/9 pass; backend restart sạch log; `/api/gallery/root`, `/api/gallery/browse?path=instagram`, `/api/accounts/scan-from-disk`, `/api/stats/overview`, `DELETE /api/media/*`, `PATCH /api/settings` đều đúng status. TypeScript `tsc --noEmit` sạch.

Open còn lại (cần policy / nhiều test fixture): `instagram-cookie-required`, `tiktok-cookie-contract`, `media-event-extension-gap`, `twitter-newest-file-heuristic`, `download-no-deadline`, `download-live-e2e-missing`, `test-coverage-thin`.

## Cập nhật UI redesign — 2026-10-14

- Nguồn trạng thái phase và danh sách thiếu sót: `docs/REDESIGN-PLAN.md` §10/§10b.
- Phase 0 đã có design tokens, fonts (Inter/Inter Tight/JetBrains Mono), app shell, brand mark và primitives `PageHeader`, `EmptyState`, `PlatformDot`, `StatusDot`, `ShortcutChip`.
- Phase 1 đã có palette quick-add global (`Ctrl/⌘K`), URL detection Instagram/X/TikTok, pill row, queue summary ba nền tảng và active stop/resume controls; không có Pause vì backend chưa cung cấp pause endpoint.
- Sửa `frontend/app/gallery/page.tsx`: `useGalleryStream` nhận `path`, không phải `streamPath`.
- Verification gần nhất: `npx tsx lib/detect.test.ts` 12 checks pass; `npm run type-check` pass; `npm run build` pass; 6 dashboard API smoke checks qua frontend proxy đều HTTP 200.
- Phase 2 Downloads đã bổ sung table/list toggle, URL-synced q/platform/status/source/view + back/forward restoration, “Tải thêm” infinite pagination, Ctrl/Cmd-click + Shift range, ArrowUp/Down + Space/Enter + Esc. `download-filters.test.ts`: 3 checks pass; type-check/build pass; downloads API HTTP 200.
- Phase 2 runtime Docker chưa verify: Next host process chiếm port 3000, Uvicorn host process chiếm port 8000; user yêu cầu giữ server host hiện tại, không dừng process. PostgreSQL container hiện stopped.
- Runtime regression follow-up: user cho phép restart đúng hai Next dev process tree của repo; một Next dev server hiện chạy qua tracked process `bgp_139bd2ed1001Mgk4q0vYI3nn62`, backend Uvicorn giữ nguyên. Sau restart routes `/`, `/downloads`, filtered downloads/gallery, `/jobs`, `/accounts`, `/settings` đều HTTP 200; backend health/downloads/jobs/accounts/settings cũng HTTP 200. Frontend log không có exception.
- Verification suites: backend `9 passed` (Pydantic deprecation warning), URL detector 12 checks, filter helper 3 checks, production build pass, type-check pass khi chạy tuần tự. Docker DB container vẫn stopped/orphan; compose không khai báo service `postgres` nên DB container runtime chưa được khôi phục.
- Phase 0/1 chưa được đánh dấu hoàn tất theo đầy đủ §13: còn visual screenshot, browser keyboard/mutation verification, responsive và light mode. Phase 2–6 vẫn có gap; xem bảng + progress log trong `docs/REDESIGN-PLAN.md`.

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

## Session — 2026-10-14

### 1. Bug: Job #4 treo không chạy + TikTok 403

**Vấn đề:** User report job chạy TikTok (@luutrwuynh_) không tải được gì.

**Root cause điều tra:**
- Docker container restart không kill được subprocess cũ → job #4 bị orphaned, DB row vẫn `running` nhưng process đã chết
- Job #4 trong DB: `status=running, total_processed=0, new_files_count=0` (đang treo từ lần trước)
- gallery-dl trả `403 Forbidden` cho cả host Windows lẫn container Docker — cùng IP public `42.115.249.102` (VNPT/Vinaphone, Việt Nam)

**Test đã làm:**
- gallery-dl 1.32.16, không cookie → 403
- gallery-dl 1.32.16, có cookie (43 keys đầy đủ: sessionid, ttwid, msToken) → 403
- yt-dlp 2026.8.19, có cookie, profile URL → `Unable to extract secondary user ID`
- yt-dlp 2026.8.19, có cookie, video URL cụ thể → `Your IP address is blocked from accessing this post`

**Kết luận:** Không phải cookie, không phải tool version. IP `42.115.249.102` (VNPT VN) bị TikTok WAF block cứng. Cookie vẫn hợp lệ.

**Fix đã làm:**
1. `backend/app/services/tiktok.py` line 30: `cookies_required = False → True` — khi chưa upload cookie sẽ error sớm thay vì treo 90s+403
2. Update DB: `jobs SET status=STOPPED WHERE id=4`, `downloads SET status=FAILED WHERE id=5`
3. Install `yt-dlp` 2026.8.19 trong container Docker (trước đó container không có yt-dlp)

**Hạn chế:** Không thể fix TikTok 403 vì IP bị block — user cần đổi IP (VPN / 4G hotspot) hoặc chờ TikTok unblock.

### 2. Plan redesign toàn bộ web-app

Đã đọc skill `web-design-engineer`, explore codebase, chọn anchor Linear + Raycast.

**Output:**
- `docs/REDESIGN-PLAN.md` — plan đầy đủ 13 mục (design system, 6 page plan, component mới, roadmap 6 phase, anti-patterns, DoD)
- `.cursor/skills/redesign-quick-card.md` — tóm tắt 1 trang

**Design direction:** Linear / Raycast (Modern Builder Tool / Dark / Hairline / Keyboard-first / Power-user)

**Tokens chính:**
```
ground    #0B0B0E   accent   #E8C547
surface-1 #131318   IG dot   #C7A8FF
surface-2 #1A1A20   X dot    #6BA6FF
surface-3 #23232B   TikTok   #FF7AA8
ink       #F4F4F5   success  #4ADE80
ink-2     #A1A1AA   warn     #F5A524
ink-3     #6B6B75   error    #F87171
radius max 20   font display Inter Tight 600
```

**6 page plan:** Dashboard ⌘K / Downloads table / Gallery lightbox / Jobs timeline / Accounts grid / Settings accordion
**Roadmap:** 6 phase, ~2-3 tuần, 1 PR mỗi phase

---

## Session — 2026-10-14 (cont.)

### 6. Code review + bug log `docs/BUGS.md`

Sau khi user chạy `/code-review` (đọc lại toàn codebase, đánh giá lỗi/điểm mạnh/điểm yếu/mở rộng, chấm 6.5/10), user yêu cầu:
- Hệ thống đang chạy **SQLite** (`backend/data/igdownloader.db`, 482 accounts, 144k media, ~144GB), KHÔNG còn Docker DB. Có 1 stale python process (uvicorn) chạy port 8000 + 1 stale node process port 3000 từ session trước. Sẽ xoá 2 PID này và tạo fresh dev setup.
- Tổng hợp các lỗi phát hiện vào **`docs/BUGS.md`** (vừa tạo) với cấu trúc Open / Resolved / Won't Fix. Cập nhật trạng thái mỗi lần sửa.

**Trạng thái hiện tại (`docs/BUGS.md`):**
- **Open (12 bugs):** 1 🔴 treeview-empty (gallery WS race), 1 🟠 stale-jobs-running (3 job RUNNING 3 ngày không reset), 10 🟡 (datetime deprecated, settings noop, filetime heuristic, gallery monolith, classify dup, test coverage, sidebar poll, delete media orphan, run-pending stale reset, safe path edge)
- **Resolved:** 0
- **Won't Fix:** 0

**Verification:**
- `GET /api/jobs?status=running` xác nhận 3 stale jobs (id=60, 65, 66) từ 11/10/2026.
- `GET /api/stats/overview` trả `jobs_running: 3` (sai UX) nhưng `downloads_24h: 0, last_download_at: null`.
- Code inspection `frontend/lib/websocket.ts:305-320` xác nhận `drainPending` có vòng lặp pass vô dụng (không re-derive pending) → xoá mất children khi batch gửi trước parent.
- `frontend/lib/websocket.ts:236` xác nhận bug 1: `key, args` thay vì 1 object `{key, args}` — deps `[key]` không tự reset khi path thay đổi, đã note trong BUGS.

**Skip / risk:**
- Chưa reset 3 stale jobs — sẽ làm khi implement fix bug stale-jobs-running (thêm lifespan startup).
- Chưa test fix trên browser, chỉ verify qua API.
- Các bug 🟡 cosmetic / refactor (gallery monolith, classify dup) ưu tiên thấp, chưa lên lịch fix.

---

### 3. Audit progress redesign + Phase 2 (Downloads Table)

Đọc lại plan + audit codebase → xác định:

**Đã xong:**
- Phase 0: Foundation (tokens, fonts, layout shell, 7 component mới: BrandMark, PlatformDot, ShortcutChip, StatusDot, PageHeader, EmptyState, CommandPalette) ✅
- Phase 1: Dashboard + ⌘K CommandPalette ✅ (~60%)
- Phase 5: Accounts page grid/list ✅ (~70%)

**Đang làm tiếp: Phase 2 — Downloads Table view**

Đã rewrite `frontend/app/downloads/page.tsx`:
- `StatusDot` (8px) thay status badge text
- `PlatformDot` thay icon đơn thuần cho 1 platform column
- Hover-only actions (retry/delete) — `opacity-0 group-hover:opacity-100`
- Sticky filter bar với 3 nhóm pills (Platform + Status + Source) 1 dòng
- Bulk action bar trượt xuống khi multi-select (transition 300ms → fix bằng conditional render + `animate-in fade-in slide-in-from-bottom-2`)
- "Xem thêm" pagination thay prev/next
- `EmptyState` khi list rỗng với CTA "Thêm URL ở Dashboard hoặc bấm ⌘K"
- `PageHeader` thay header inline

**Live test (12:45-12:51 PM, 14/10/2026):**
- Start backend uvicorn port 8000 + Next dev port 3000 song song
- API `/api/health` ✅, `/api/downloads` trả 31 mục
- Page load 200, hiển thị 30 rows
- Visual match plan: PageHeader "31 mục", StatusDot 8px xanh cho "Hoàn tất", filter pills đẹp, "Xem thêm (30 / 31)" enabled
- Fix: bulk action bar conditional render thay CSS transition (Tailwind JIT không pick được `pointer-events-none` đúng cách)

**Build pass:** `npx tsc --noEmit` ✅ + `npx next build` ✅ + browser visual ✅

**Skip / risk:**
- Chưa test hover row → action button visibility (chỉ check default state, hover test fail do browser MCP)
- Chưa test multi-select flow end-to-end (chỉ check default empty state)
- Phase 3 Gallery + Phase 4 Jobs + Phase 6 Settings chưa audit

### 4. Phase tiếp theo (ưu tiên)

- Phase 3: Gallery Lightbox + Drawer (cần component Lightbox riêng)
- Phase 4: Jobs timeline + detail page
- Phase 6: Settings accordion + DropZone

### 5. Servers đang chạy (background)

- Backend: `uvicorn app.main:app --host 127.0.0.1 --port 8000` — shell 723622
- Frontend: `next dev -p 3000` — shell 723623
- Stop: `Get-NetTCPConnection -LocalPort 3000,8000 -State Listen | ForEach-Object { taskkill /F /T /PID $_.OwningProcess }`

### File mới tạo trong session

| File | Mục đích |
|------|----------|
| `docs/REDESIGN-PLAN.md` | Plan redesign đầy đủ |
| `.cursor/skills/redesign-quick-card.md` | Tóm tắt 1 trang |

---

*Cập nhật: 2026-10-14 bởi Cursor Agent*
