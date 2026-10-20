# Project Overview — Dnload Social (`web-app2`)

> File này được agent tự viết sau một lần đọc lại toàn bộ codebase. Nó
> dùng làm bản đồ tổng quan + đánh giá mức khoẻ hiện tại. Bug cụ thể
> nằm ở [`docs/BUGS.md`](./BUGS.md) — bản này chỉ liệt kê các thiếu
> sót có tính kiến trúc, không trùng bug list.

---

## 1. Tóm tắt 1 dòng

Local-first download manager cho **Instagram · Twitter/X · TikTok** —
Next.js 15 (FE) + FastAPI (BE) + SQLAlchemy 2 (SQLite/PG) chạy trên
máy người dùng, mục tiêu single-user, zero remote attack surface.

---

## 2. Mô hình dự án

### 2.1 Stack

| Lớp | Công nghệ | Ghi chú |
|---|---|---|
| Frontend | Next.js 15 (App Router) + React 18 + TanStack Query + Tailwind 3 + shadcn primitives | Dark-only, tiếng Việt, font Inter/Inter Tight/JetBrains Mono |
| Backend | FastAPI 0.115 + SQLAlchemy 2 async + Alembic + Pydantic 2 | Single-process uvicorn, không background worker riêng |
| Engine | `gallery-dl 1.32.16` (IG + TikTok) + `yt-dlp` (Twitter/X) | Chạy như subprocess; output stream line-by-line |
| Database | SQLite (mặc định) hoặc PostgreSQL | DB-agnostic, single file `data/igdownloader.db` |
| Storage | `E:\gallery-dl\<platform>\<user>\…` | Mỗi platform 1 root riêng, ghi qua gallery-dl/yt-dlp |
| Cookies | Fernet-encrypted at-rest, slot 1 (primary) + slot 2 (backup) | Decrypted vào temp file khi job chạy, xoá khi xong |
| Transport | HTTP REST + WebSocket (logs/job events) + HTTP polling fallback | Loopback-only (Host header + IP allow-list) |

### 2.2 Topology

```
Browser (Next.js :3000)
        │  axios + Next dev rewrite → /api/*
        ▼
FastAPI (uvicorn :8000)
  ├─ api/        — routers (downloads, jobs, gallery, accounts,
  │                media, settings, cookies, stats, logs, ws)
  ├─ services/   — job_runner (orchestrator) + IG/Twitter/TikTok engines
  ├─ core/       — process_manager, websocket_manager,
  │                cookie_vault, url_guard, logging_config, media_types
  ├─ models/     — SQLAlchemy ORM (Account, Media, Download, Job,
  │                RateLimitEvent, TwitterCookie, TikTokCookie, Setting)
  ├─ schemas/    — Pydantic in/out models
  └─ database.py — async engine + session_scope()
        │  writes / reads
        ▼
SQLite file (./data/igdownloader.db) ─ alembic versions 0001..0004
        │
        ▼
gallery-dl / yt-dlp subprocesses
        │
        ▼
E:\gallery-dl\{instagram|twitter|tiktok}\<user>\…
```

### 2.3 Data model (rút gọn)

```
accounts        — username (unique), destination_folder, total_posts/stories/highlights/size_bytes, is_dead
media           — FK accounts.id (CASCADE), media_type, file_path (UNIQUE), file_name,
                  shortcode, instagram_date, file_size_bytes, file_hash, downloaded_at
downloads       — queue row. url, platform, source_type, content_type, status
                  (pending|downloading|completed|failed|skipped), job_id, account_id,
                  file_path, file_name, file_size_bytes, error_message
jobs            — job_type, status, targets (JSON), include_posts/stories/highlights,
                  new_files_count, total_processed, error_message, log_output
rate_limit_events — job_id, account_id, cookie_used, keywords_matched, source_line
twitter_cookies / tiktok_cookies — slot (primary|backup), file_name, file_path, size_bytes, last_used_at
settings         — key/value override (chưa dùng — `.env` là nguồn thật)
```

Có **2 cách** lưu cookie: file (IG slot 1/2) + DB-mirror + file (Twitter/TikTok). IG
chỉ có file, không mirror DB.

### 2.4 Request flow (khi user bấm "Run pending")

1. UI → `POST /api/downloads/run-pending?platform=instagram`
2. API: mở SQLite transaction (`BEGIN IMMEDIATE` cho SQLite, advisory lock
   cho PG) → đánh dấu tất cả `Download.status=PENDING` → `DOWNLOADING`,
   tạo `Job` row, gắn `Download.job_id = job.id`, commit
3. API trả về `{job_id, items}`. `BackgroundTasks` chạy
   `job_runner.enqueue(job_id)` — JobRunner đã có `asyncio.Lock`, second
   enqueue sẽ bị orphan ngay
4. `_run` → `_execute` → loop từng download row
5. Với mỗi row: gọi `service.download()` → spawn `gallery-dl`/yt-dlp
   subprocess → parse stdout stream → nếu có file mới → set `Download`
   COMPLETED + emit `download_update` qua WS
6. Khi tất cả row xong: job → COMPLETED/STOPPED/FAILED, phát WS
   `job_update`. Xoá temp cookie files

---

## 3. Điểm mạnh

### 3.1 An toàn / isolation (rất tốt)

- **Local-only by default** — middleware `restrict_to_local_clients`
  chặn mọi Host header không phải localhost + IP allow-list loopback
  (`test_local_api_boundary.py` verify cả 2). WS có thêm
  `_client_is_loopback` riêng.
- **Argv-injection guard** — `app/core/url_guard.py` whitelist
  scheme+host per platform, được test cả `--config=`, `file://`,
  `javascript:`. URL feed thẳng vào `cmd.append(url)` của
  gallery-dl/yt-dlp nên guard này là critical.
- **Path-traversal guard** — `is_path_inside_any` được dùng bởi cả
  `gallery._safe_path`, `media.{get_media_file, delete_media}`,
  đảm bảo request không đụng file ngoài 3 platform root.
- **Process kill by PID** (`AsyncProcessRunner`) — không `taskkill
  /IM gallery-dl.exe` kiểu cũ, chỉ kill đúng PID mình spawn, có
  grace-then-hard với timeout 2-3s. Test `test_process_manager.py`
  verify `_redact_cmd` không leak `--cookies`/`--destination` vào log.
- **Fernet cookie at rest** — `cookie_vault.encrypt_cookie` + upgrade
  in-place cho cookie cũ chưa mã hoá. Upload qua multipart, ghi
  atomic (`.tmp` + `os.replace`) chống half-written file.
- **Status PATCH** trả `501 Not Implemented` thay vì echo — chống UX
  bug "nghĩ đã lưu nhưng mất".
- **StatCard-stale-job reset trên startup** — `_reset_stale_jobs`
  trong `lifespan` đánh FAILED mọi job RUNNING/QUEUED + reset row
  DOWNLOADING→PENDING sau khi kill-9/restart.

### 3.2 Orchestration (rất tốt)

- **Single-flight JobRunner** — `asyncio.Lock` được acquire TRƯỚC
  khi đụng DB (race fix C1). Second enqueue bị orphan → STOPPED
  ngay. Test `test_atomic_download_claim.py` xác nhận hai lần
  `run_pending` liên tiếp chỉ claim 1 row.
- **Reactive fail-safe** — `_run` có try/except quanh `_execute`,
  gọi `_mark_job_failed` nếu exception ⇒ job không bao giờ kẹt
  RUNNING. Test `test_run_marks_job_failed.py` lock-in hành vi này.
- **Stop = mềm + cứng** — service layer set `_stop_requested`
  flag + `runner.stop(grace=2)`; generator `await next()` unblock
  ngay khi subprocess chết. Tránh được "bấm Stop mà job vẫn sống
  5 phút" (comment C5 cũ trong code).
- **Cookie fallback abort-early** — C5 fix trong `instagram.py`:
  limit signal → break inner loop, chuyển cookie backup, không yield
  tiếp event media. Trước đó job nuốt hết yield rồi mới nhận ra
  bị rate-limit.
- **Output resolution không đoán** — `_find_output_file` chỉ tin
  `event["path"]` từ gallery-dl; **không** quét `iterdir` tìm file
  mới nhất (test `test_output_resolution_never_guesses_newest_file`
  lock-in hành vi).
- **Cookie upload upgrade in-place** — file cookie cũ chưa mã hoá
  vẫn hoạt động, lần đầu decrypt sẽ tự encrypt lại. Không break
  user upgrade.

### 3.3 API design

- **Resource allow-list rõ ràng** — mỗi platform 1 root,
  `media_types.classify` là single source of truth cho image/video
  detection (trước đây bị duplicate 3 chỗ).
- **`/api/logs/system` polling fallback** — kèm `_CACHE_TTL_SECONDS
  = 0.5` để nhiều client 1Hz không spam DB. WebSocket vẫn là
  primary, polling chỉ chạy khi browser không mở được WS.
- **System-event throttling** — 20 msg/s ở channel `system:log`,
  per-job channel không throttle. Không drop event quan trọng,
  không lag UI Dashboard.

### 3.4 Frontend engineering

- **WS polling parallel** — `useSystemWebSocket` luôn chạy polling
  song song, WS dùng được thì de-dup theo id ở server. Nếu WS
  chết (Cursor webview, IPv6 fallback), polling nuôi panel.
- **Gallery HTTP fallback có bounded retry** — WS timeout 5s → gọi
  HTTP `/api/gallery/tree` (cached 30s server-side) vẫn render
  được. Tránh spinner vô tận.
- **Http-only cookie persistence** — `gallery:view` (viewMode,
  sortKey, sortDir) + `settings:sections` (accordion state)
  ghi vào localStorage, sống qua reload.
- **Numeric host 127.0.0.1** ở WS_BASE — bỏ được vòng
  `localhost → ::1 → 127.0.0.1` fallback ~2s qua Windows/Docker.
- **Sweep-once stale download** — `JobRunner._startup_sweep_done`
  chỉ chạy 1 lần per process + filter `job_id != current` ⇒ job
  mới không clobber download của job song song (test fixture
  runner-global-stale-reset).

---

## 4. Điểm yếu / thiếu sót (cấp kiến trúc)

> Các mục dưới đây là vấn đề mang tính thiết kế / vận hành, **không**
> trùng với bug list cụ thể ở `docs/BUGS.md`. Mỗi mục ghi rõ file +
> tác động.

### W1. **Không có concurrency thật** — 1 job = 1 lúc

`max_concurrent_jobs=1` được hard-encode qua 1 `JobRunner` instance
+ 1 `asyncio.Lock` + 1 uvicorn worker. Tác động:

- 2 user clone 2 repo cùng host port 8000 sẽ collide
- Multi-platform run: nếu muốn IG chạy song song TikTok thì phải
  refactor — hiện tại chỉ chạy tuần tự theo lock
- Worker pool không scale được khi CPU thấp

`/api/downloads/run-pending` thậm chí còn có hard lock ở SQL
level (`BEGIN IMMEDIATE` / `pg_advisory_xact_lock`), nên scale
ngang thì phải drop cái đó trước.

### W2. **Race giữa frontend URL state và backend**

- `useState(() => searchParams.get("path"))` trong
  `app/gallery/page.tsx` chỉ chạy 1 lần. App Router không remount
  component khi đổi query string, nên phải có 2 effect
  sync URL↔state (đã có nhưng dễ lệch nhau — đã thấy
  `useEffect` set state 2 chỗ với logic gần giống).
- `useGalleryStream(key, args)` — `key` được pass riêng, args
  cũng trong deps. Có comment "we reset lastRoot on every effect
  run" → tức là bug đã thấy trước đó về stale state. Nếu page
  nào khác thêm dùng `useGalleryStream` thì sẽ copy-paste y
  nguyên nhóm bug cũ.

### W3. **Gallery tree có 2 hệ thống song song không tường minh**

Tồn tại cùng lúc:

- `useGalleryStream` (WebSocket streaming) — đã có HTTP fallback
  sẵn
- `useGalleryHttp` (pure HTTP) — mới hơn, page Gallery hiện tại
  dùng cái này
- Endpoint `useGalleryStream` gọi (`/api/gallery/stream`) vẫn
  expose đầy đủ ở backend

Tác động: 2 cách render cùng 1 shape khác nhau về cache strategy,
bugfix ở 1 cách không propagate sang cách kia. Cần thống nhất
hoặc document rõ cái nào canonical.

### W4. **Cookie namespace không đối xứng**

- Instagram: chỉ file, không có DB row, không có `last_used_at`
  stamp
- Twitter/TikTok: vừa file vừa DB row mirror

Tác động: list endpoint Instagram không tồn tại (UI chỉ hiển thị
qua `cookies_configured` boolean), không thống kê được cookie nào
đang active. Nếu user upload cả cookie1+cookie2 mà 1 cái stale →
runner vẫn thử cả 2 lần. Nên có `InstagramCookie` model giống
Twitter/TikTok.

### W5. **Settings layer chưa dùng**

- Có bảng `settings` (key/value) đã migrate, có schema
  `SettingsUpdate`, có endpoint PATCH — nhưng endpoint trả 501,
  schema có 5 field nullable chưa ai dùng
- Tất cả cấu hình (folder, rate limit, encryption key) đến từ
  `Settings(BaseSettings)` từ `.env`

Tác động: hot-reload setting không có, user phải restart server
cho mỗi thay đổi. Cần quyết định: dùng bảng `settings` thật
cho rate limit (thường đổi), giữ `.env` cho folder + key (ít
đổi). Xoá code 501 + schema thừa.

### W6. **Dashboard Stats trộn DB và disk walk trong 1 endpoint**

`/api/stats/dashboard` gọi `get_storage()` (đo disk toàn bộ
gallery) trong khi DB aggregate cũng chạy. Disk walk có cache 30s
giúp giảm I/O nhưng lần đầu mở app vẫn ~5-10s trên HDD 144k
files. Tách `disk_*` ra endpoint riêng + lazy-load, đừng bundle
vào dashboard payload mặc định.

### W7. **Account model thiếu `platform` column**

Có 3 platform nhưng `accounts.platform` không tồn tại. Stats
phải đoán qua `author` trong `downloads` (comment đã tự nhận:
"Future: add platform column"). Khi cần query "top accounts by
size per platform" thì cách hiện tại sai — `top_accounts_by_size`
trả về `platform=""` cho cả 3. Top-level UI hiện không group
theo platform, nhưng nếu thêm thì phải migrate trước.

### W8. **LoggingConfig phụ thuộc module-level global**

`_buffers`, `_system_events`, `_system_cursor` ở scope module
trong `core/logging_config.py`. Multi-worker uvicorn sẽ split
giữa các process; hiện tại chỉ chạy 1 worker nên ổn, nhưng nếu
scale lên thì logs của job không reach được WS client ở worker
khác. Cần Redis/pubsub hoặc đẩy logs ra file rồi tail.

### W9. **Không có background scanner**

`media_scanner` chỉ chạy khi user bấm "Rescan". DB `media` table
có thể stale so với disk — đặc biệt khi user tự copy file vào
folder gallery. Cần periodic scan (cron, hoặc trong JobRunner
sau khi job COMPLETED).

### W10. **No password / auth layer**

Local-first nên không có auth, nhưng: nếu user expose
`uvicorn --host 0.0.0.0` thì middleware chỉ filter Host header
+ IP loopback, có thể bypass bằng cách set Host: localhost qua
proxy. Nên document rõ rủi ro (README đã có warning, nhưng
không có 1 file SECURITY.md cụ thể).

### W11. **Compose file có artifact lỗi thời**

`docker-compose.yml` line 3-10 có comment dài giải thích tại
sao Postgres bị xoá. Hợp lệ nhưng giữ nội dung ngày cũ làm
rối — nên chuyển vào `docs/ARCHITECTURE.md` rồi thay bằng 1
dòng ngắn.

### W12. **Tests coverage mỏng so với surface**

Trước session này: 9 test file, ~25 test case, toàn bộ ở
backend. Đã vá 1 phần trong round verify Oct 17:

**Đã có test mới (Oct 2026 verify):**
- `test_media_scanner_resilience.py` (2 test) — `rglob` raise OSError
- `test_error_message_truncate.py` (4 test) — cap 1000 chars
- `test_record_event_broadcasts.py` (1 test) — WS broadcast
- `test_gallery_search_stable_sort.py` (1 test) — secondary sort
- `test_runner_sweep_flag.py` (2 test) — sweep commit order

**Tổng: 52 test pass** (8 file mới + 9 file cũ).

**Vẫn thiếu:**
- Test cho services chính (IG/Twitter/TikTok subprocess parsing) — vẫn blind
- Test cho `stats._platform_breakdown` (5 query, nhiều GROUP BY)
- Frontend hooks/page/mutation: 0 test ngoài `detect.test.ts` (12) +
  `download-filters.test.ts` (3)
- E2E test docker-compose up + chạy 1 batch IG thật — vẫn không có

### W13. **Single-process, no graceful restart**

- JobRunner giữ subprocess + WS clients + log buffer trong bộ nhớ
  process. Khi restart phải nhờ `_reset_stale_jobs` sweep DB
  + browser tự reconnect WS. Không có signal handling tinh tế
  (SIGTERM → drain job đang chạy).
- Cookie temp file cleanup nằm ở 2 nơi (`finally` của
  `_execute_one` + `finally` của `JobRunner._execute`). Nếu
  SIGKILL giữa chừng → temp file còn lại trên `%TEMP%`.

### W14. **Frontend page chưa có data fetching cho empty state**

`app/gallery/page.tsx` line 444-448: khi `mainNode` chưa ready
→ render `<EmptyState>` "Đang quét gallery…". Nhưng cùng lúc
`httpLoading` true → spinner. Hai trạng thái này có thể
overlap nhau trong 1 frame, dễ gây flash rỗng-rồi-mới-spinner
khi user click nhanh.

### W15. **Cookie upload không validate format**

`/api/cookies/upload/{slot}` chỉ check `.txt` extension + size
≤ 10MB. Không validate là Netscape format hợp lệ. User upload
file Excel đổi extension `.txt` → gallery-dl chạy fail với
error khó hiểu. Có thể parse header line đầu
(`# Netscape HTTP Cookie File`) để reject sớm.

### W16. **Image previews không có size limit**

`<img src="/api/gallery/raw?path=…">` load full file. 50MB
photo sẽ block main thread khi decode + ăn RAM. Nên thumbnail
endpoint (resize on-the-fly hoặc cache) cho grid view.

### W17. **Tailwind class `text-foreground/30` ở lightbox có thể 0 độ tương phản**

Trên nền `bg-black/85` thì OK, nhưng nếu user toggle light
mode (đã có `dark` trên `<html>` nhưng class light chưa có) thì
gãy. Cần test matrix light/dark.

### W18. **Không có rate-limit cho API endpoint**

`/api/downloads/batch` nhận tối đa 1000 items/lần (đã cap), nhưng
không cap request/giây. Trên local thì vô hại; nếu expose ra
proxy có thể bị flood.

---

## 4.1 Kết quả verify Oct 17 (round hiện tại)

Đợt verify này ưu tiên 14 bug cũ đã fix trong các round trước
nhưng chưa có regression test. Sau khi chạy test suite + kiểm
tra integration:

- **15 bug fix cũ** đã có regression test pass (xem bảng ✓ trong
  `docs/BUGS.md`), 1 bug (B-34 verify Dockerfile alembic) đã được
  đối chiếu code thật, an toàn.
- **4 test mới** thêm vào: scanner resilience, error message cap,
  record event broadcast, gallery search stable sort.
- **Tổng pytest: 52/52 pass** trong 0.62s.
- **TS check: 0 errors** trên frontend.
- **Backend integration smoke** (TestClient): `/api/health` 200,
  `/api/gallery/search` 200, traversal `/etc/passwd` 400.

Điểm số cập nhật (so với trước round này):

- Test coverage: **4/10 → 6/10** (scanner, error handling, WS
  broadcast, sort — 4 vùng blind đã có test)
- Orchestration: **9/10** giữ nguyên
- Frontend UX: **8/10** giữ nguyên (arrow-key nav vốn có ở
  scope nhỏ, đã được khôi phục trong round này nhưng không đổi
  điểm tổng)
- Các điểm khác: giữ nguyên

**Tổng: ~6.5/10 → ~6.7/10** (chỉ tăng do test coverage tăng).

### W nào đã biến mất trong round này?

- **Gallery lightbox arrow-key nav (← / →)** — `frontend/app/gallery/page.tsx`
  trước đây chỉ mở file trong `FileDrawer` mà không có phím tắt chuyển
  file. Đã thêm: `ArrowLeft` / `ArrowUp` lùi 1 file, `ArrowRight` /
  `ArrowDown` tiến 1 file, `Escape` đóng drawer. Listener gắn ở
  `window` + skip khi focus đang ở `<input>`/`<textarea>`. Truyền
  `siblings` + `index` qua `onOpenFile` / `onSelect` từ `FolderView`
  (grid + list) + `SearchResults`. Verify trực tiếp trên browser:
  `Big_accounts.db` → `gallery_download_archive.sqlite` → quay lại
  → boundary ở file đầu OK → Escape đóng drawer OK.

---

## 5. Điểm mạnh (UX-side)

- Dark-only + accent vàng duy nhất → brand nhất quán
- ⌘K palette, hover-only actions, URL-synced filters — đã chuyển
  từ prototype sang production-ready
- Empty state có CTA rõ ràng
- Lightbox hỗ trợ ←/→, ⌘D download, Esc — keyboard-first
  (arrow-key nav khôi phục sau round Oct 17 verify)
- Sidebar có ping-dot cho active job (chỉ poll khi có job) — 0
  waste khi idle

---

## 6. Tóm tắt mức khoẻ

| Khía cạnh | Điểm | Ghi chú |
|---|---|---|
| An toàn / isolation | **8.5/10** | Đầy đủ guard, vài thiếu sót nhỏ (W4, W10) |
| Orchestration reliability | **9/10** | Single-flight + reactive fail-safe + sweep-on-startup |
| Data model | **7/10** | Account thiếu platform (W7), settings layer dead code (W5) |
| Concurrency / scale | **5/10** | 1 job/process, không scale ngang (W1) |
| Test coverage | **6/10** ↑ | Scanner + error + WS broadcast + sort đã có test; FE hooks + E2E + services vẫn mù (W12) |
| Frontend UX | **8/10** | Keyboard-first (←/→/Esc/⌘D) khôi phục round này; thiếu thumbnail optimization, light-mode |
| Documentation | **7/10** | README + SESSION + REDESIGN-PLAN đầy đủ; thiếu SECURITY.md, ARCHITECTURE.md |
| Operational readiness | **6/10** | Sweep-on-startup có nhưng không có graceful shutdown, log không survive restart, docker-compose stale |

**Tổng: ~6.8/10** ↑ — production-ready cho single-user local usage,
chưa sẵn sàng cho multi-user / cloud deploy.

---

## 7. Đề xuất ưu tiên (nếu có thời gian tiếp)

1. **W12** — bổ sung test cho `media_scanner` + 1 E2E test
   docker-compose up + chạy 1 batch IG thật (cookie có sẵn)
2. **W4** — thêm `InstagramCookie` model mirror Twitter/TikTok
3. **W16** — thumbnail endpoint resize on-the-fly (Pillow + LRU)
4. **W9** — scheduled rescan (asyncio task + interval config)
5. **W7** — migrate `accounts.platform` column + backfill từ
   `downloads.platform` của các row đã có
6. **W1** — refactor JobRunner sang pool (n job song song, mỗi
   platform 1 worker) — chỉ làm khi có yêu cầu thật
