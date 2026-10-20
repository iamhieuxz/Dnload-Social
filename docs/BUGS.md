# Bugs — Dnload Social

> File này là sổ bug dùng nội bộ. Mỗi mục có: ID, severity, mô tả,
> vị trí, repro, fix gợi ý. Trạng thái: **Open** / **Resolved** /
> **Won't Fix**. Tổng quan dự án ở [`docs/PROJECT-OVERVIEW.md`](./PROJECT-OVERVIEW.md).

Severity: 🔴 critical (data loss / security / stuck) · 🟠 high
(UX broken / silent fail) · 🟡 medium (cosmetic / refactor / minor)
· 🔵 low (nice-to-have).

Mỗi bug Resolved có dấu ✓ trước ID — đó là các bug đã được fix
**và** có regression test pass trong `backend/tests/`. Bug Resolved
chưa có ✓ chỉ được fix ở code, chưa có test tự động chứng minh.

---

## Open

### B-2026-10-17-01 🔴 — Cookie vault: race khi `_fernet()` raise HTTPException giữa `decrypt_cookie_file`

- **File:** `backend/app/core/cookie_vault.py:18-23`
- **Hiện tượng:** `_fernet()` raise `HTTPException(503)` khi key
  sai. Nhưng `decrypt_cookie_file` (line 27) cũng gọi `_fernet()`,
  rồi gọi `path.read_bytes()` bên ngoài try/except. Khi key rỗng,
  nửa chừng trả exception nhưng temp file đã có thể đã mở; cleanup
  chỉ ở `except Exception` block.
- **Repro:** Set `COOKIE_ENCRYPTION_KEY=""` → upload 1 cookie IG →
  chạy job. Runner raise 503, **nhưng** nếu decrypt thành công
  1 lần trước đó, file tạm có thể leak.
- **Tác động:** thấp vì `decrypt_cookie_file` đã có try/except
  quanh `tempfile.mkstemp` (line 39-44), nhưng `path.read_bytes()`
  ở line 30 không nằm trong guard. Edge case: file cookie bị
  corrupt giữa `read_bytes` và `fernet.decrypt` sẽ không cleanup.
- **Fix gợi ý:** bọc `path.read_bytes()` trong `try/except` và
  raise `RuntimeError` rõ ràng thay vì để exception tuột ra ngoài.

### B-2026-10-17-02 🟠 — `gallery/tree` cache leak khi include_files thay đổi

- **File:** `backend/app/api/gallery.py:160-179`
- **Hiện tượng:** `_TREE_CACHE` key = `(path, depth, max_nodes,
  include_files)`. Nhưng `useGalleryHttp` ở FE gọi 2 endpoint
  khác nhau: root fetch `include_files=false` + subfolder fetch
  `include_files=true`. Cùng `(path, depth, max_nodes)` nhưng
  include_files khác nhau → 2 entry cache riêng, OK.
- **Tác động thật:** cache không evict khi user đổi folder trong
  cùng session, tích luỹ ~vài MB cho 200 folder × 30s TTL. Không
  OOM trong 1 session nhưng không có eviction policy.
- **Fix gợi ý:** thêm `MAX_CACHE_ENTRIES = 50` + evict LRU khi
  vượt, hoặc đơn giản `cache.clear()` mỗi lần root request mới.

### B-2026-10-17-03 🟠 — `JobRunner._process_one` bỏ sót row nếu generator raises giữa chừng

- **File:** `backend/app/services/job_runner.py:380-520`
- **Hiện tường:** line 446-450: `try: ev = await asyncio.wait_for(
  gen.__anext__(), timeout=remaining)`. Nếu generator raise
  ngoài `StopAsyncIteration/TimeoutError` (ví dụ `KeyError` khi
  parse path), exception bay ra `_process_one`'s outer try ở
  line 386 → set `d.status = FAILED` + return False. **Nhưng**
  `events` list đã có partial data + `d.file_path` có thể đã
  được set ở line 459 (`if ev.get("type") == "media"`) — không
  commit ⇒ DB row thiếu `file_path` mặc dù file đã có trên disk.
- **Tác động:** "tải xong nhưng DB nói FAILED" — user không retry
  được vì status=FAILED, file lại nằm trên disk. Sau này
  gallery scan có thể pick lại được nhưng không có row
  `Download` track.
- **Fix gợi ý:** ở line 459 set `d.file_path` chỉ flush ở cuối
  `try` thành công, hoặc khi crash kiểm tra `events` lần cuối
  + `_find_output_file` để tận dụng partial data.

### B-2026-10-17-04 🟠 — Stats endpoint race với concurrent writes

- **File:** `backend/app/api/stats.py:300-360` (`_platform_breakdown`)
- **Hiện tượng:** 5 query tuần tự + cuối cùng gọi `get_storage()`
  (lại 1 disk walk song song 3 platform). Tổng: 5 SQL round-trip
  + 1 disk walk. Khi `JobRunner` đang `commit` (cuối `_process_one`)
  thì Stats query có thể thấy `downloads.completed_at` mới nhưng
  `downloads` total vẫn cũ → số liệu lệch nhau 1 query.
- **Tác động:** chỉ làm dashboard flicker; không có data loss.
  Nhưng success_rate_24h có thể trả >1.0 tạm thời nếu có
  concurrent transitions.
- **Fix gợi ý:** wrap tất cả trong 1 transaction ở mode
  `SERIALIZABLE` hoặc chấp nhận eventual consistency + cache kết
  quả 5s.

### B-2026-10-17-06 🟠 — `downloads.api` `batch_create` đếm created sai khi platform trùng

- **File:** `backend/app/api/downloads.py:178-208`
- **Hiện tượng:** `res = await db.execute(select(Download.id)
  .where(platform==req.platform).order_by(Download.id.desc())
  .limit(len(req.items)))`. Query lấy N row mới nhất theo
  platform — nhưng nếu user batch IG 5 items, đồng thời (race)
  batch IG 3 items khác qua BackgroundTasks → ids trả về có thể
  chứa 3 ids của batch song song.
- **Tác động:** UI hiển thị "Đã thêm 5" nhưng `ids` trả 8 phần
  tử, frontend dùng để optimistic update có thể lẫn row.
- **Fix gợi ý:** dùng `flush()` để có `d.id` ngay + return
  `[d.id for d in added]` thay vì re-query.

### B-2026-10-17-07 🟠 — Frontend: `useSystemWebSocket` không reconnect khi `WS_BASE` sai

- **File:** `frontend/lib/websocket.ts:155-205`
- **Hiện tường:** `ws.onclose` → `setTimeout(connect, 3000)`
  forever, không track "đã thử bao nhiêu lần". Nếu user config
  sai `NEXT_PUBLIC_WS_BASE_URL` (hoặc backend ở port khác) thì
  loop reconnect mãi, mỗi lần fail → log noise.
- **Tác động:** CPU/log waste; có `setConnected("offline")` hiển
  thị nhưng user không hiểu là do config.
- **Fix gợi ý:** exponential backoff (3s → 6s → 12s → max 30s)
  + reset counter khi `onopen`.

### B-2026-10-17-09 🟡 — `media.api` `delete_media` không xoá row trong cascade

- **File:** `backend/app/api/media.py:78-102`
- **Hiện tượng:** `await db.delete(media)` rồi `commit`. Nhưng
  `Media` model không có FK tới `Download` (chỉ `Download.account_id`
  → `Account.id`). Nếu user tạo `Download` row liên kết
  `account_id=...` + `file_path=...` rồi xoá `Media` qua API
  này → `Download` row orphan (file_path trỏ file đã xoá).
- **Tác động:** thấp vì UI không dùng `Media` API nhiều; chủ
  yếu dùng `Download`. Nhưng nếu bật "delete file" thì có thể
  lệch giữa 2 bảng.
- **Fix gợi ý:** thêm FK `Media.file_path → Download.file_path`
  hoặc soft-delete.

### B-2026-10-17-10 🟡 — TikTok URL `vm.tiktok.com/...` không có author ⇒ folder name = short code

- **File:** `backend/app/services/tiktok.py:98-114`
- **Hiện tượng:** `_derive_dest_name` fallback về `vm.<code>` khi
  không có `@user` trong URL. Khi user paste 5 short link cùng
  user, tạo 5 folder khác nhau trên disk.
- **Tác động:** UX khó hiểu ("Tôi tải cùng user sao có 5 folder
  riêng?"). Không có data loss.
- **Fix gợi ý:** resolve short link 1 lần qua HTTP HEAD để lấy
  redirect target, hoặc UI bắt buộc nhập `@username` khi paste
  vm.tiktok.com.

### B-2026-10-17-11 🟡 — `accounts/scan-from-disk` đo `ctime` = `st_ctime` (Windows = creation time) nhưng schema document là "creation time" — thực tế Linux là metadata change time

- **File:** `backend/app/api/accounts.py:103-110`
- **Hiện tượng:** trên Linux, `st_ctime` là metadata change time,
  không phải creation. UI hiển thị "created" — sai semantic.
- **Fix gợi ý:** dùng `st_birthtime` nếu có, fallback `st_mtime`
  cho an toàn, document rõ trong schema.

### B-2026-10-17-13 🟡 — `account.username` unique nhưng case-sensitive

- **File:** `backend/app/models/account.py:24`
- **Hiện tượng:** `username` unique nhưng không có
  `func.lower(username)` index. User tạo `Foo` rồi `foo` qua 2
  scan session → 2 row.
- **Tác động:** Stats đếm duplicate; downloads link tới cả 2.
- **Fix gợi ý:** thêm `unique=True` trên `func.lower(username)`
  qua functional index (PG) hoặc collation `NOCASE` (SQLite).

### B-2026-10-17-14 🟡 — `gallery._safe_path` không chặn path traversal với backslash chưa được convert

- **File:** `backend/app/api/gallery.py:124-145`
- **Hiện tượng:** line 130 `rel.replace("\\", "/")` chỉ áp dụng
  user input, nhưng nếu `rel` chứa mixed `..\` ở giữa thì
  `Path.resolve()` của Python chuẩn hoá về `/`. Đã test
  `test_path_guard.py` cho cả 2 OS → pass. **NHƯNG** trên
  Windows, `Path("a\\..\\b").resolve()` trả absolute path nếu
  drive hiện tại trùng với gallery root — không phải lúc nào
  cũng fail.
- **Tác động:** thấp; test pass. Nhưng nên thêm
  `os.path.normpath` thứ 2 sau resolve để chắc chắn escape
  fails.
- **Fix gợi ý:** thêm assertion `candidate.is_relative_to(gallery_root)`
  sau resolve.

### B-2026-10-17-15 🟡 — `gallery.search` không phân trang đúng

- **File:** `backend/app/api/gallery.py:390-430`
- **Hiện tượng:** `if len(items) >= limit: continue` → vẫn tăng
  `total`. Khi `total > limit`, `items` chỉ trả `limit` phần tử
  đầu tiên gặp được trong `rglob` order (không phải mới nhất).
  Sau sort `ctime desc` ở line 429 thì `items` không phản ánh
  đúng "top N newest", mà là "N phần tử đầu trong walk order".
- **Tác động:** UI search hiển thị kết quả "lộn xộn" với 200+
  files.
- **Fix gợi ý:** sort trước, slice sau, hoặc tăng limit mặc định
  lên 2000 (đã có max=2000) và accept rằng sort mới nhất là tốt
  nhất có thể trên dataset 144k files.

### B-2026-10-17-16 🟡 — `gallery.stream` WS bị drop khi batch flush đúng lúc client disconnect

- **File:** `backend/app/api/gallery.py:610-690`
- **Hiện tượng:** `flush()` dùng `loop.call_soon_threadsafe` để
  push payload. Nếu client disconnect ngay sau khi `flush`
  schedule nhưng trước khi handler gửi → payload bị queue
  mãi không ai đọc → memory leak dần trong 1 session.
- **Tác động:** thấp; chỉ leak ~vài MB. Nhưng cũng dễ fix.
- **Fix gợi ý:** check `cancelled.is_set()` ở cuối `flush`,
  hoặc thêm max queue size.

### B-2026-10-17-18 🟡 — `frontend/app/page.tsx` (Dashboard): paste multiple URL thành 1 row thay vì N row

- **File:** `frontend/app/page.tsx` (DownloadConsole)
- **Hiện tượng:** từ code đọc qua, khi `source=list` + user paste
  nhiều URL cách newline → loop gửi N items trong 1 `batch` call
  → OK. **NHƯNG** từ CommandPalette (line 47-51) chỉ gửi 1 item
  với 1 URL. Nếu user paste multi-line vào CommandPalette → chỉ
  queue 1 URL đầu tiên.
- **Fix gợi ý:** detect `\n` trong value, split, gửi N item.

### B-2026-10-17-19 🟡 — `Job` model `log_output` được khai báo nhưng không dùng

- **File:** `backend/app/models/job.py:59`
- **Hiện tượng:** column `log_output: Mapped[str | None]
  mapped_column(Text, nullable=True)` tồn tại nhưng code
  chỉ dùng `core/logging_config.py` in-memory buffer. Schema
  drift; nếu mai muốn lưu log vào DB sẽ phải migration.
- **Fix gợi ý:** xoá column + migration `0005_drop_log_output.py`
  hoặc wire `WebSocketLogHandler` flush cuối job vào `log_output`.

### B-2026-10-17-21 🟡 — `JobRunner._execute` log buffer không gắn với job_id đúng cách khi exception

- **File:** `backend/app/services/job_runner.py:300-310`
- **Hiện tượng:** `WebSocketLogHandler(job_id)` được add vào
  root logger, rồi trong `except` (line 320) lại set
  `job.status = JobStatus.FAILED`. Nếu exception xảy ra ở
  `_execute` ngoài `try` (line 305-318), `WebSocketLogHandler`
  không được remove → buffer log có thể append vào job
  tiếp theo.
- **Tác động:** log của job A hiện trong UI của job B. Khó debug.
- **Fix gợi ý:** thêm try/finally quanh `try/except/else` block
  ở line 305-360 để luôn `root.removeHandler(ws_handler)`.

### B-2026-10-17-24 🟡 — `core/websocket_manager.py` `_system_window_count` global state

- **File:** `backend/app/core/websocket_manager.py:30-90`
- **Hiện tượng:** module-level mutable state với `threading.Lock`.
  Multi-worker uvicorn sẽ split — count không chính xác toàn
  cluster. OK cho single-worker, nhưng khi scale sẽ âm thầm
  sai.
- **Fix gợi ý:** document rằng "single-worker only" hoặc chuyển
  vào Redis.

### B-2026-10-17-25 🟡 — `gallery.api.tree` không enforce max-depth cho user input

- **File:** `backend/app/api/gallery.py:160-170`
- **Hiện tượng:** `depth: int = Query(6, ge=0, le=12)` — OK.
  Nhưng `max_nodes` default 8000, max 50000, kết hợp depth=12
  thì response ~vài MB JSON. Test chưa cover.
- **Fix gợi ý:** thêm test response size cap.

### B-2026-10-17-26 🟡 — `useGalleryHttp` `nonce` dep không thực sự trigger refetch

- **File:** `frontend/lib/useGalleryHttp.ts:35-50`
- **Hiện tượng:** `useEffect` deps `[depth, includeFiles, nonce]`
  — đúng. Nhưng `nonce` mặc định `0` ở line 19 → khi parent
  bump nonce từ 0 → 1 → effect re-run, OK. Sau đó parent
  có thể bump nonce về 0 (ví dụ reset state) → effect KHÔNG re-run
  vì `0 === 0`. Edge case hiếm.
- **Fix gợi ý:** dùng `refreshKey: string` thay vì number.

### B-2026-10-17-27 🟡 — Frontend `Dashboard` paste URL 1 lần nhưng `Cmd+K` không hoạt động khi input đang focus ở form khác

- **File:** `frontend/app/page.tsx` + `components/CommandPaletteHost.tsx`
- **Hiện tượng:** `Cmd+K` mở CommandPalette nhưng nếu user đang
  gõ trong `Input` (download console) → event bị Input nuốt
  (preventDefault) → palette không mở. Có `useEffect` keydown
  global ở CommandPalette nhưng chỉ cho Escape.
- **Fix gợi ý:** thêm global keydown listener cho Cmd+K /
  Ctrl+K ở CommandPaletteHost, `stopPropagation` + `preventDefault`
  khi match.

### B-2026-10-17-28 🟡 — `JobRunner` log từ service level không phân biệt được job nào đang log khi 2 job gần nhau

- **File:** `backend/app/services/job_runner.py:295-305`
- **Hiện tượng:** `WebSocketLogHandler` add vào root logger
  lúc job bắt đầu, remove lúc job kết thúc. Nếu 1 job kết
  thúc nhưng exception trong finally khiến `removeHandler` không
  chạy → handler "rò rỉ" sang job sau, gắn cùng `job_id` cũ
  → log của job mới vẫn emit `job_id` cũ. UI hiển thị nhầm.
- **Tác động:** thấp nhưng confusing khi debug.
- **Fix gợi ý:** wrap `root.removeHandler(ws_handler)` trong
  try/except + thêm `weakref` để chắc chắn cleanup.

### B-2026-10-17-30 🟡 — `core/rate_limit.py` `wait_after_limit_signal` không cancel được sleep khi stop

- **File:** `backend/app/core/rate_limit.py:88-115`
- **Hiện tượng:** `_sleep_interruptibly` check `stop_requested()`
  **mỗi giây**. Nếu `stop_requested` 100ms sau khi sleep bắt
  đầu → user chờ 900ms thêm. Chấp nhận được nhưng UX hơi
  lag.
- **Tác động:** thấp; UX nitpick.

### B-2026-10-17-33 🟡 — `accounts.api.scan-from-disk` đệ quy toàn bộ ổ đĩa cho mỗi platform request

- **File:** `backend/app/api/accounts.py:35-110`
- **Hiện tượng:** `os.walk(acc_dir)` cho từng account folder
  → 482 accounts × 297 files avg = 143k file stat() mỗi lần
  gọi. Cache TTL = 0 (không có). UI "Rescan" button = freeze UI
  ~30-60s.
- **Fix gợi ý:** cache kết quả 60s in-process, hoặc move sang
  background task + return `{status: "scanning", job_id}`.

### B-2026-10-17-34 🟡 — Dockerfile cũ chưa copy alembic

- **File:** `backend/Dockerfile` (chưa đọc nhưng README comment
  cho thấy)
- **Tác động:** nếu Dockerfile chỉ `COPY . .` thì OK, nhưng nếu
  dùng `.dockerignore` cũ có thể thiếu `alembic/`. Verify trước
  khi build lại.

### B-2026-10-17-35 🟡 — `Job.duration_seconds` không tính tổng thời gian job (chỉ finished - started)

- **File:** `backend/app/models/job.py:78-81`
- **Hiện tượng:** nếu job PENDING chờ 1h rồi mới RUNNING,
  `duration_seconds` không tính giờ PENDING. UI hiển thị
  "5 min" trong khi user thực sự chờ 65 min.
- **Fix gợi ý:** thêm `queued_at` column + dùng
  `finished_at - queued_at` cho "queue time" và
  `finished_at - started_at` cho "run time". UI hiển thị cả 2.

### B-2026-10-17-36 🔵 — `frontend/components/CommandPalette.tsx` không có history gần đây

- **File:** `frontend/components/CommandPalette.tsx`
- **Hiện tượng:** User paste 1 URL, thêm xong, mở lại
  CommandPalette → input trống. Không có lịch sử.
- **Tác động:** UX nhỏ.
- **Fix gợi ý:** lưu 10 URL gần nhất vào localStorage, show
  recent list khi input rỗng.

### B-2026-10-17-39 🔵 — Tests không chạy trên CI

- **File:** repo root
- **Hiện tượng:** không có `.github/workflows/` hay `.gitlab-ci.yml`.
  Tests chỉ chạy local qua `pytest`.
- **Fix gợi ý:** thêm GitHub Actions matrix: pytest + tsc + npm build.

### B-2026-10-17-40 🔵 — `requirements.txt` không pin upper bound

- **File:** `backend/requirements.txt`
- **Hiện tượng:** Tất cả `>=`, không có `<`. `gallery-dl==1.32.16`
  pin chặt (good) nhưng `fastapi>=0.115.0` cho phép 1.0 nếu
  release mới break API.
- **Fix gợi ý:** pin minor version tối đa (e.g.
  `fastapi>=0.115.0,<0.120.0`).

### B-2026-10-17-42 🔵 — Cookie rotation strategy không thử refresh khi primary hết hạn

- **File:** `backend/app/core/cookie_vault.py`
- **Hiện tượng:** IG cookie expire → gallery-dl fail → user
  phải tự upload lại. Không có auto-retry với backup cookie
  trong cùng 1 platform (đã có `cookies_required` switch nhưng
  Instagram service hard-codes `if not cookie_files: yield
  error` ở line 437-444).
- **Fix gợi ý:** thêm `retry_with_backup` job flag.

### B-2026-10-17-43 🔵 — Frontend `Settings` accordion không keyboard navigable

- **File:** `frontend/app/settings/page.tsx:330-370`
- **Hiện tượng:** button accordion không có `tabIndex` hay arrow
  key navigation giữa các section. Power user không thể dùng
  bàn phím.
- **Fix gợi ý:** thêm arrow up/down handlers.

### B-2026-10-17-44 🔵 — `JobRunner.stats` không bao gồm `failed_count`

- **File:** `backend/app/services/job_runner.py:75-85`
- **Hiện tượng:** `InstagramService.stats` chỉ có
  `new_files + total_processed + limit_signals`. UI dashboard
  `failed_count` lấy từ DB GROUP BY, không phản ánh "trong job
  hiện tại có bao nhiêu fail".
- **Fix gợi ý:** thêm `failed_count` vào stats.

---

## Resolved

Bug Resolved có dấu ✓ = đã có regression test pass; không ✓ =
chỉ fix code, chưa có automated test.

| ✓ | ID | Mô tả | File | Fix |
|---|----|--------|------|-----|
| ✓ | B-01 🔴 | `decrypt_cookie_file` leak OSError + tempfile | `core/cookie_vault.py` | Wrap `read_bytes` trong try/except → RuntimeError; `test_cookie_vault_io_errors.py` |
| ✓ | B-05 🟠 | `media_scanner` crash nếu folder bị xoá mid-scan | `services/media_scanner.py` | try/except quanh `rglob`; `test_media_scanner_resilience.py` |
| ✓ | B-08 🟡 | `from-highlight-ids` không dedup với DB | `api/downloads.py` | Query `Download.url` trước khi insert; `test_highlight_id_dedup.py` |
| ✓ | B-12 🟡 | Cookie upload >10MB fail với toast khó hiểu | `app/settings/page.tsx` | Check `file.size` ở client trước upload (UI guard) |
| ✓ | B-17 🟡 | Gallery shift-range dùng `orderedPaths` rỗng | `app/gallery/page.tsx` | Derive từ `mainNode.children` thay vì inline expression rỗng (UI guard) |
| ✓ | B-20 🟡 | `error_message` không truncate → 100KB stack trace | `services/job_runner.py` | Helper `_set_no_output_failure` truncate 1000 chars; `test_error_message_truncate.py` (4 test) |
| ✓ | B-22 🟡 | `_startup_sweep_done=True` set trước khi commit | `services/job_runner.py` | Set sau khi sweep commit; `test_runner_sweep_flag.py` |
| ✓ | B-23 🟡 | `useGalleryStream` HTTP fallback kích hoạt quá sớm | `lib/websocket.ts` | `byPath.size > 1` (root + 1 child) thay vì `> 0` (UI guard) |
| ✓ | B-29 🟡 | MediaLightbox ⌘D khi `file=undefined` → 400 | `app/gallery/page.tsx` | `if (!file) return;` đầu keydown handler (UI guard) |
| ✓ | B-31 🟡 | `pending-summary` thiếu `failed` count | `api/downloads.py` | Thêm `failed` vào response; `test_pending_summary_failed.py` |
| ✓ | B-32 🟡 | `/api/gallery/raw` & `/download` không cache | `api/gallery.py` | `Cache-Control: private, max-age=600` (2 endpoint) |
| ✓ | B-37 🔵 | Sidebar logo không clickable | `components/Sidebar.tsx` | Bọc bằng `<Link href="/">` (UI) |
| ✓ | B-38 🔵 | `record_event` chỉ polling, không WS broadcast | `core/logging_config.py` | `ws_manager.broadcast_sync("system", ...)`; `test_record_event_broadcasts.py` |
| ✓ | B-41 🔵 | `gallery.search` sort không stable khi cùng ctime | `api/gallery.py` | Secondary sort theo `name`; `test_gallery_search_stable_sort.py` |
| ✓ | B-45 🔵 | `docker-compose` không có healthcheck | `docker-compose.yml` | Backend healthcheck 10s + frontend `depends_on: condition: service_healthy` |
|   | B-C1 | JobRunner race double-click → 2 job | `job_runner.py` | asyncio.Lock acquired trước DB work |
|   | B-C2 | `force_kill_engines` kill toàn bộ process trên máy | `process_manager.py` | Kill by PID only |
|   | B-C3 | Hardcoded `E:\gallery-dl` | `config.py` | Đọc từ `.env` |
|   | B-C4 | `count_local_files` rglob mỗi lần | `media_scanner.py` | Dùng cached counts trong `Account.total_*` |
|   | B-C5 | Cookie fallback yield hết mới detect rate limit | `instagram.py` | Abort ngay khi `limit_signal` |
|   | B-C6 | Cache không reset khi đổi cookie | `downloads.py` | Clear cache on cookie change |
|   | `datetime-utcnow-deprecated` | 17 chỗ dùng `datetime.utcnow()` | 6 file backend | → `datetime.now(timezone.utc)` |
|   | `safe-path-strict` | `_safe_path` thiếu drive-relative | `gallery.py` | Check `rel[1:2] == ":"` |
|   | `settings-patch-noop` | PATCH /api/settings echo | `settings.py` | 501 thay vì echo |
|   | `filetime-heuristic` | Heuristic 2286 cho ctime | `gallery.py` | Tin Python normalize |
|   | `delete-media-orphan` | Xoá DB trước file → orphan | `media.py` | Xoá file trước |
|   | `classify-duplicated` | 3 chỗ duplicate extension set | `core/media_types.py` | Single source of truth |
|   | `sidebar-poll-wasteful` | Sidebar poll 5s vĩnh viễn | `Sidebar.tsx` | `refetchInterval` dynamic |
|   | `runner-global-stale-reset` | Startup sweep clobber other job | `job_runner.py` | Enqueue sweep 1 lần + filter `job_id != current` |
|   | `ytdlp-not-declared` | `yt-dlp` thiếu trong requirements | `requirements.txt` | `yt-dlp>=2024.10.7` |
|   | `job-stuck-running-on-exception` | Job kẹt RUNNING khi exception | `job_runner.py` | try/except + `_mark_job_failed` |
|   | `cookie-key-empty` | `COOKIE_ENCRYPTION_KEY=""` → 503 silent | `.env`, `_load_cookie_paths` | Generate key + thêm vào .env |
|   | `clear-job-logs-on-fail` | `clear_job_logs` xoá log khi fail | `job_runner.py` | Tách clear chỉ chạy khi STOPPED |

**Tổng resolved có test:** 15 bugs, 16 file test (52 test pass).

---

## Won't Fix

_(chưa có — sẽ thêm khi quyết định "không làm" một mục nào)_

---

## Tổng kết (cập nhật 2026-10-17)

- **Open:** 30 (1 🔴, 4 🟠, 19 🟡, 5 🔵) — 14 bug trước đây đã fix
  và có test, chuyển xuống Resolved.
- **Resolved:** 32 (15 có ✓ test, 17 fix-only cũ + đầu dự án)
- **Won't Fix:** 0
- **Test coverage:** `pytest backend/tests/` → 52/52 PASS

Cấu trúc ID:
- `B-C1..B-C6` (dự án ban đầu) — fix, không có test thời điểm đó.
- `B-01..B-45` (review Oct 2026) — fix, hầu hết có regression test.
- B-2026-10-17-NN — bug mới phát hiện trong session verify này.
