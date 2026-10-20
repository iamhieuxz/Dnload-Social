# Fix Checklist — theo thứ tự ưu tiên bug

Trạng thái: [x] xong · [ ] todo

## Baseline → Hiện tại

| | Trước | Sau |
|---|---|---|
| backend tests | 52 passed | **60 passed** |
| frontend tests | **FAIL** — không chạy được | **24 passed** |
| `tsc --noEmit` | 8 lỗi | **0 lỗi** |
| `next build` | fail (type error) | **pass** |

## P0 — chặn release

- [x] **B1. Frontend tests không chạy được**
      → `vitest@5` + `vitest.config.mts` + script `npm test`.
      Hai file test cũ chuyển từ script `console.error`/`process.exit` sang
      `describe/it`. **15 passed.**
      Verify: ✅ `npm test`

- [x] **B2. Download thành công bị đánh dấu FAILED**
      `_find_output_file` trả `None` khi không có event `media.path`
      (profile đã tải trước / profile rỗng / TikTok URL) → `_set_no_output_failure`
      → **luôn** FAILED.
      → Đổi signature thành `_set_no_output_failure(d, events)`. Không có `error`
        event **và** có `skip`/`no_output` ⇒ **SKIPPED**; còn lại ⇒ FAILED.
        `_process_one` xử lý 2 nhánh (FAILED → return False, SKIPPED → return True
        nhưng không tính là lỗi).
      Verify: ✅ `test_no_output_is_not_failure.py` (5 case) + 4 test cũ cập nhật

- [x] **B3. Async generator không `aclose()`**
      Break khỏi vòng lặp (deadline / stop / error) mà không close generator ⇒
      mất `finally` teardown subprocess + xoá temp cookie.
      → Bọc `try/finally`, luôn `await gen.aclose()`.
      Verify: ✅ `test_generator_aclose.py` (3 case). **Đã chứng minh test bắt
      đúng bug** — xoá `aclose()` → 2 fail.
      Ghi chú: phải assert `closed` **bên trong** event loop. `asyncio.run()` gọi
      `loop.shutdown_asyncgens()` khi teardown, nên assert sau đó luôn xanh.

## P1 — sửa tuần này

- [x] **B4. `run_pending` giữ SQLite write-lock quá lâu**
      Claim **phải** atomic (BEGIN IMMEDIATE / advisory lock) — nếu không,
      2 request đồng thời sẽ cùng thấy PENDING rows và tạo 2 job.
      Cái sửa được là **thời gian giữ lock**: trước đây 1 UPDATE per row (5k row
      = 5k round trip dưới lock). Giờ 1 bulk UPDATE.
      Verify: ✅ `test_atomic_download_claim.py` vẫn pass

- [x] **B5. Gallery sort folder theo `ctime` — không đúng ý user**
      `ctime` của thư mục là thời điểm **tạo**, không đổi sau đó ⇒ folder tải
      hằng ngày luôn giữ nguyên vị trí. User muốn "folder nào vừa tải file" ⇒
      `mtime` của thư mục (bump mỗi lần có file mới).
      → Tách ra `lib/gallery-sort.ts`: folder dùng `mtime`, file dùng `ctime`,
        tie-break bằng tên cho ổn định.
      Verify: ✅ `gallery-sort.test.ts` (9 case), có case chứng minh `ctime`
      cho kết quả sai

- [x] **B6. Scratch files trong repo**
      → Xoá 20 file (`diag_*`, `backend/_*.py`, `*_backend.out/err`,
        `*_frontend.out/err`, `x_tool3.py`) + bổ sung `.gitignore`.
      Verify: ✅ `git status` chỉ còn source thật

- [x] **B7. CI**
      → `.github/workflows/ci.yml`: backend (pytest + import check) và
        frontend (test + type-check + build).
      Verify: ✅ cả 3 command đều pass local trước khi commit

## P2

- [x] **B10. `docker-compose.yml`: bỏ `version:` deprecated**
      Verify: ✅ `docker compose config --quiet` pass

- [x] **B11. Pydantic `class Config` → `ConfigDict`**
      `schemas/download.py` — `class Config: from_attributes = True` (deprecated,
      removed in v3) → `model_config = ConfigDict(from_attributes=True)`.
      Verify: ✅ 60 passed, **0 warning** (trước có 1 PydanticDeprecatedSince20)

- [x] **B8. ~~`session` giữ mở xuyên suốt job~~ — ĐÃ KIỂM CHỨNG: SAI**
      Review ban đầu nói "connection bị giữ tới 30 phút". **Sai.**
      Đo thật với SQLAlchemy async:
      ```
      after execute,        checked out: 1
      after commit,         checked out: 0
      after 3x execute+commit, checked out: 0
      ```
      `commit()` trả connection về pool. `_process_one` commit sau **mỗi** row
      ⇒ connection được trả về giữa các lần ghi. Không có connection nào bị
      giữ suốt job, nên `pool_size=5` / `max_conflow=20` không bị ảnh hưởng.
      **Không sửa gì.** Ghi lại để không ai đôi sửa nhầm vô.

- [ ] **B9. Tách `frontend/app/page.tsx`** (~1.120 dòng chứa Dashboard +
      form queue + LiveTerminal + stats). Không làm vì nó là refactor thuần
      hình thức, không sửa được bug nào, và rủi ro regression cao hơn giá trị.
      Nên làm khi có việc thực tế cần sửa trong file đó.

---

## Xác nhận bằng app thật (chạy backend + frontend, tay vào disk)

### B5 — Gallery sort ✅
317 folder thật trong `E:\gallery-dl\instagram`:

| folder | ctime (tạo) | mtime (file mới nhất) |
|---|---|---|
| `trquynh_luu_` | **07-01 05:44** | **10-14 03:05** |
| `maichi60.65` | 09-26 03:28 | 10-13 12:35 |

`trquynh_luu_` tạo từ tháng 7 nhưng vừa nhận file 14/10. Sort `ctime` xếp
nó ngoài top 8; sort `mtime` đưa vào top 6. UI khớp **10/10** với API ở cả
`asc` lẫn `desc` (đối chiếu tên 10 folder đầu).

### B2 — Download "xong" không còn bị tag lỗi ✅
Chạy thật 3 job:

| job | input | kết quả | status | error |
|---|---|---|---|---|
| 143 | TikTok video mới | tải file mới | `completed` | null |
| 144 | TikTok video **đã có** | `[SKIP]` | `completed` | null |
| 145 | IG `lth.na` (3.680 file, đã tải đủ) | `[ERR] no_output` → **`skipped`** | `skipped` | **null** |

Job 145 chính là bug bạn báo: tải xong / không còn gì để tải mà bị gắn lỗi.
Trước fix nó là `failed` + "No output file found". Giờ `skipped`, và
`Downloads` page hiển thị *"3 mục trong hàng đợi · đã tải 3"* — không tag
lỗi đỏ nào.

### B3 — generator leak
Không tái hiện được bằng tay (cần nhiều timeout liên tiếp). Đã verify bằng
test đã chứng minh bắt đúng bug — xem mục B3 ở trên.

---

## Sửa thêm khi làm CI

Không nằm trong kế hoạch nhưng phải làm để `next build` không đỏ:
- `gallery/page.tsx`: dùng helper `isImageExt`/`isVideoExt` sẵn có thay vì
  inline array, `node.ext` là optional nên `.includes(node.ext)` lỗi type
- `gallery/page.tsx`: nút Download dùng `asChild` không tồn tại trong `Button`
  → render `<button><a></a></button>` (invalid HTML). Đổi thành `<a>` + export
  `buttonVariants` từ `button.tsx`
- Dead code: `sortKey === "mtime"` (không còn là `SortKey`)