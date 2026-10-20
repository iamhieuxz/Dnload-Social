# Dnload Social — Web Redesign Plan

> Kế hoạch redesign toàn bộ giao diện web. Đây là tài liệu dùng cho lần sau — không chứa code, chỉ chứa hướng đi + design system + roadmap thực thi.

---

## 1. Tóm tắt dự án

- **Tên sản phẩm:** Dnload Social (tên cũ: IG Downloader)
- **Loại:** Local-first download manager cho Instagram · Twitter/X · TikTok
- **Stack hiện tại:** Next.js 15 + React + Tailwind + shadcn-style UI · FastAPI + SQLAlchemy (PostgreSQL/SQLite)
- **Người dùng:** power-user cá nhân / dev Việt Nam — chạy self-hosted, quen CLI, dùng cookie thủ công
- **Mục tiêu redesign:** Làm app "đáng để khoe" — từ tool nội bộ trở thành sản phẩm open-source có design language rõ ràng, dễ onboard cho người mới mà vẫn giữ được mật độ thông tin cho power user.

## 2. Design Read + 5 dials

```yaml
Design Read:
  artifact: local-first multi-platform download manager (dashboard + library + jobs + settings)
  audience: power-user / dev, self-host, biết CLI, cần mật độ cao
  visual-language: linear / raycast — Modern Tool / Builder SaaS
  mode: redesign · overhaul (giữ route + IA, thay toàn bộ visual + interaction)
  visual-variance: 6   # các page có look khác nhau một chút (gallery grid vs queue table vs settings)
  motion-intensity: 4   # micro-interactions snappy, không có motion kể chuyện
  information-density: 8   # power-user thấy nhiều info là tốt
  asset-dependence: 2   # gần như không cần hình ảnh, dùng icon + dữ liệu thật
  brand-fidelity: 7   # xây brand identity riêng, không bắt chước 100%
```

## 3. Anchor & Recipe

**Anchor chính:** `linear` (modern builder tool, dark, hairline, restraint)
**Anchor phụ:** `raycast` (keyboard-first, soft glass, accent dot per platform)

Lý do: app hiện đã gần DNA linear (dark + hairline + neutral + 1 accent vàng). Giữ DNA đó, polish thêm, lấy thêm từ raycast:
- Shortcut chip ⌘K cho mọi action chính
- Glass / floating command palette cho Quick Add
- Per-platform accent dot (IG tím, X xanh, TikTok hồng) — mỗi platform 1 chấm nhỏ 4px, không phả full brand

## 4. Design system

```markdown
Design Decisions:
- Design Read: local-first power-user tool, dark, high information density
- Anchor: linear (primary) + raycast (secondary) — Modern Tool / Builder SaaS
- Color palette (dark, warm):
    - ground:        #0B0B0E      # nền page, slightly warm
    - surface-1:     #131318      # card, panel
    - surface-2:     #1A1A20      # raised, hover
    - surface-3:     #23232B      # active, focused input
    - hairline:      rgba(255,255,255,0.07)
    - ink:           #F4F4F5      # text chính
    - ink-2:         #A1A1AA      # text phụ
    - ink-3:         #6B6B75      # muted, hint
    - accent:        #E8C547      # vàng đậm, dùng cho CTA, active state, focus ring
    - accent-soft:   rgba(232,197,71,0.12)
    - platform dots: IG #C7A8FF, X #6BA6FF, TikTok #FF7AA8  # mỗi cái 1 dot 4-6px, không phả full color
    - success:       #4ADE80
    - warn:          #F5A524
    - error:         #F87171
- Typography:
    - display:   "Inter Tight" weight 600, letter-spacing -0.02em
    - body:      "Inter" 14px / 1.55, weight 400-500
    - mono:      "JetBrains Mono" 12-13px cho path, URL, log, shortcut chip
    - KHÔNG dùng Inter weight 400 cho heading
- Spacing: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64
- Radius: 6 (button, input) / 10 (card) / 14 (modal) / 20 (command palette)
              → không bao giờ trên 20
- Shadow:
    - rest:    none
    - raised:  0 1px 0 rgba(255,255,255,0.04) inset, 0 0 0 1px hairline
    - float:   0 12px 32px rgba(0,0,0,0.45), 0 0 0 1px hairline  # dùng cho command palette, popover
- Motion:
    - hover:   120ms ease-out
    - press:   80ms ease-out
    - layout:  320ms cubic-bezier(0.22, 1, 0.36, 1)
    - palette: 180ms spring nhẹ khi mở/đóng
- Icon: Lucide, stroke 1.5, 16px mặc định, 20px cho CTA
- Focus: ring 2px accent, offset 2px — KHÔNG bỏ outline
```

## 5. Branding

App tên "Dnload Social" — giữ tên, polish logo. Logo concept:
- Khối vuông 32x32 bo góc 8, fill `accent` (`#E8C547`)
- Bên trong: 2 mũi tên xuống song song (icon Download) màu `ground` — stroke 2.5
- Header dùng chữ "Dnload" Inter Tight 600, "Social" ở weight 400
- Subtitle: bỏ "v7.0.0" — thay bằng tagline ngắn "Local · Multi-platform"

## 6. IA & Page-by-page plan

Giữ nguyên 6 route, redesign từng trang. Mỗi page có 1 dòng "vibe target".

### 6.1 Dashboard `/` — vibe: "Command center"
- **Trên:** Stat strip 4 ô (Total / Pending / Active / Failed) — `StatCards` đã có, polish typography
- **Giữa:** Quick Add console — 2 lớp tabs (platform × source) — làm thành **1 dãy horizontal pill** thay vì 2 hàng, gọn hơn
- **Quick Add 2.0:** ⌘K command palette (lấy từ raycast) — gõ URL là auto-detect platform + tạo row. Phím tắt `mod+K`
- **Dưới:** Queue summary (3 cột IG/X/TikTok) + Live terminal (chiếm 50% chiều rộng, cố định height 360px, có nút pause/clear)
- **Action bar nổi** ở góc phải dưới: Stop / Pause / Resume — pill group

### 6.2 Downloads `/downloads` — vibe: "Spreadsheet for power user"
- **Filter bar sticky** trên cùng: search + platform pill + status pill + source + view toggle (link/list/DB)
- **Table** thay cho card list:
  - Cột: checkbox · status dot · platform dot · content type · author · URL mono · size · progress bar (cho downloading) · created · actions
  - Row height 44px, hover surface-2, selected surface-3
  - Multi-select với checkbox header → bulk action bar trượt xuống từ dưới
- **Status dot 8px** thay cho badge text dài: xanh = completed, xanh dương nhấp nháy = downloading, đỏ = failed, xám = pending
- **Retry / delete** là row-hover actions (ẩn mặc định, hiện khi hover)
- **Pagination** dồn xuống dưới, nút "Load more" thay cho next/prev

### 6.3 Gallery `/gallery` — vibe: "Lightroom-lite cho download"
- **3 cột:** tree sidebar (280px) · main grid/list · detail drawer (right, 360px, slide-in)
- **Grid view:** thumbnail vuông 1:1, gap 8px, hover lift 2px, click mở drawer
- **Lightbox:** full-screen overlay, phím `←` `→` step qua sibling, `Esc` đóng, `⌘D` download
- **Breadcrumb path** dạng mono pill, click từng segment
- **Stats panel** dồn vào drawer thay vì toggle riêng
- **Sort/group:** name, date, size, kind (image/video/text)
- **Multi-select** với `Shift+click` → bulk delete/rename/move

### 6.4 Jobs `/jobs` + `/jobs/[id]` — vibe: "Cron history"
- **List view:** timeline dọc, mỗi job là 1 card mỏng với timeline marker trái
- **Card:** platform dot · targets (mono, truncate 1 dòng) · status · duration · file count · error (nếu có) — click mở detail
- **Detail page:** 2 cột — metadata bên trái (start/finish/duration/error/exit code) · live log bên phải (replay từ DB, không chỉ WS)
- **Tab "Files"** trong detail: bảng file sinh ra từ job này

### 6.5 Accounts `/accounts` + `/accounts/[id]` — vibe: "Contact book"
- **List:** card grid 3 cột, mỗi card = avatar (initial 2 chữ) + username + platform dot + last synced + download count
- **Top action:** "+ Add account" mở modal, gõ username + chọn platform
- **Detail page:** profile header (avatar 64x64 bo tròn, bio, stats) · tab Posts/Stories/Highlights cho IG, Tweets/Videos cho X · button "Add to queue" mở Quick Add với sẵn account đó

### 6.6 Settings `/settings` — vibe: "DevTools panel"
- **3 sections** dạng accordion sticky:
  1. **Storage** — 3 ô read-only: IG folder, X folder, TikTok folder, cookie folder (mở trong Explorer bằng nút)
  2. **Cookies** — 3 nhóm IG/X/TikTok, mỗi nhóm 2 slot (primary/backup), upload drop zone + size + last used
  3. **Rate limit** — 4 slider số: min delay, max delay, batch size, batch cooldown
- **Cookies section** là phần quan trọng nhất — làm rõ "cookie hết hạn" warning với badge đỏ + nút "Refresh"

## 7. Component cần tạo mới

| Component | Mục đích | File đề xuất |
|---|---|---|
| `CommandPalette` | ⌘K global Quick Add | `components/CommandPalette.tsx` |
| `PlatformDot` | 4-6px dot màu theo platform | `components/PlatformDot.tsx` |
| `ShortcutChip` | `⌘K`, `↵` — dùng mono + hairline | `components/ShortcutChip.tsx` |
| `StatusDot` | 8px dot thay cho status badge | `components/StatusDot.tsx` |
| `BulkActionBar` | slide-up bar khi multi-select | `components/BulkActionBar.tsx` |
| `Lightbox` | full-screen image/video viewer | `components/Lightbox.tsx` |
| `DropZone` | file upload drag-drop | `components/DropZone.tsx` |
| `Slider` | shadcn Slider wrap | `components/ui/slider.tsx` |
| `EmptyState` | icon + heading + 1 action — dùng khi list rỗng | `components/EmptyState.tsx` |
| `PageHeader` | h1 + subtitle + action group — thay cho header inline | `components/PageHeader.tsx` |

## 8. State & interaction mới

- **Command palette** mở bằng `mod+K`, scope detection theo URL pattern (ig.com → Instagram, tiktok.com → TikTok, twitter.com/x.com → Twitter). Submit tạo row + toast.
- **Multi-select chuẩn linear:** click chọn, shift+click range, cmd+click toggle. Bulk action bar trượt lên ở dưới.
- **Sticky filter bar** ở Downloads, Gallery, Jobs — filter lưu vào URL params để shareable.
- **Toast gom nhóm:** "Added 12 URLs to queue" thay vì 12 toast riêng.
- **Empty state có CTA** thay vì text khô: "Chưa có download nào — paste link hoặc bấm ⌘K".
- **Loading skeleton** dạng shimmer hairline thay vì spinner xoay ở mọi chỗ.

## 9. Accessibility & responsive

- **Light mode** làm cùng token system, swap color tokens — KHÔNG hardcode màu. Ưu tiên dark mặc định.
- **Reduced motion** tôn trọng `@media (prefers-reduced-motion: reduce)` — tắt transition, giữ instant.
- **Focus ring** luôn hiển thị, không bao giờ `outline: none` không có ring thay thế.
- **Keyboard nav** đầy đủ ở table, tree, modal, palette. `Esc` đóng modal, `?` mở shortcut help.
- **Responsive:** desktop-first (vì power user dùng desktop). Breakpoint `md: 768px` cho sidebar collapse, `lg: 1024px` cho full layout. Mobile chỉ cần dashboard + downloads + gallery đọc được, không cần full feature.
- **Tiếng Việt** trong tất cả label (giữ locale Vi) — copy ngắn gọn, tránh technical jargon khi có thể.

## 10. Roadmap thực thi (ưu tiên) — TRẠNG THÁI

| Phase | Scope | Trạng thái | Ghi chú |
|---|---|---|---|
| **0. Foundation** | Design tokens, fonts, primitives, layout shell, PageHeader, EmptyState, BrandMark, ScrollToTopButton | 🟡 Đã triển khai, cần visual acceptance | Tokens theo §4, font Inter/Inter Tight/JetBrains Mono, shell và brand mark đã có. `tsc`/build đã pass sau Phase 1; light mode token swap và ảnh chụp đối chiếu chưa làm. |
| **1. Dashboard + Command palette** | ⌘K CommandPalette, Quick Add horizontal pills, StatCards polish, ActiveJobIndicator, LiveTerminal | 🟡 Đã triển khai và kiểm tra kỹ thuật | Palette global qua `CommandPaletteHost`, `Ctrl/⌘K`, URL detector cho IG/X/TikTok, global quick-add button, horizontal platform/source pills, 3-platform queue summary, active stop/resume controls, terminal 360px. Detector 12 checks, frontend type-check/build pass, Dashboard API qua proxy 6/6 HTTP 200. Chưa automated-test mutation tạo download/UI keyboard trong browser; Pause không có vì backend không có pause endpoint. |
| **2. Downloads table** | Table/list view, URL-synced filters, load more, multi-select, bulk action, status dot, keyboard nav | 🟡 Đã bổ sung và verify tĩnh/API; chưa Docker runtime | Có table/list toggle; q/platform/status/source/view đồng bộ query string và phục hồi back/forward; infinite query với Load more; Cmd/Ctrl-click toggle, Shift range, ArrowUp/Down, Space/Enter, Esc; Suspense loading shell. `download-filters.test.ts` 3 checks, `tsc`/build pass, downloads API HTTP 200. Docker runtime chưa verify vì host Next/Uvicorn đang chiếm ports 3000/8000; giữ các process theo yêu cầu user. |
| **3. Gallery + Lightbox** | Grid/list, lightbox, drawer, multi-select, search | 🟡 Đã có nền tảng; thiếu interaction | Có tree, grid/list, search, lightbox, arrow/Esc và file drawer dạng overlay. Còn thiếu persistent 360px detail column, gallery multi-select/bulk, ⌘D, URL-synced filters. Type-check từng phát hiện `useGalleryStream` nhận nhầm key `streamPath`; đã sửa thành `path` và type-check pass. |
| **4. Jobs + Accounts** | Timeline list, detail page, account cards | 🟡 Đã có nền tảng; thiếu tính năng theo plan | Routes, PageHeader/EmptyState và DB job logs đã có. Jobs list chưa là timeline cards/đủ targets-platform-error; thiếu Files tab. Accounts hiện scan thư mục, chưa có add-account/profile tabs/add-to-queue flow. |
| **5. Settings polish** | Accordion sticky, per-platform folder rows, copy-path, tiktok warn | 🟡 Đã có nền tảng; thiếu controls | Có accordion, folder rows và cookie slots. Chưa sticky; chưa DropZone, cookie expiration/refresh, rate sliders; “open Explorer” mới copy path. |
| **6. Polish** | Motion tokens rộng, EmptyState thay text khô, `?` shortcut help, a11y audit, scroll-to-top polish | ⬜ Chưa hoàn tất | Có reduced-motion, focus ring và scroll-to-top. Thiếu shortcut help, skeleton nhất quán, light mode, keyboard/responsive audit và visual acceptance. |

**Đã có component primitives:** `PageHeader`, `EmptyState`, `PlatformDot`, `StatusDot`, `ShortcutChip`, `BrandMark`, `CommandPalette`, `ActiveJobIndicator`, `ScrollToTopButton`, `JobStatusBadge`, `StatCards`, `LogStream`, `Sidebar`, `DashboardActions`, `BulkActionBar`.

**Đang dở / cần làm tiếp theo (đã đối chiếu code; không coi “có route” là phase xong):**
1. **Phase 2:** URL state/view modes/load more/Cmd-click/keyboard navigation.
2. **Phase 3:** multi-select/bulk actions, detail drawer layout, `⌘D`, URL state.
3. **Phase 4:** Jobs timeline + Files tab; xác định và xây đúng account create/detail contract trước khi thêm UI.
4. **Phase 5:** cookie dropzone/status, rate-limit write API/controls, sticky accordion.
5. **Phase 6:** global shortcut help, skeleton/motion, light mode, responsive + keyboard/accessibility + visual acceptance.

## 10b. Progress log và verification evidence

### 2026-10-14 — Runtime regression test

- Runtime ban đầu: `/`, `/gallery` HTTP 200; `/downloads`, `/jobs`, `/accounts`, `/settings` treo trong khi có hai Next dev server cùng project, dẫn tới port 3000 conflict/unclear process ownership.
- Được user cho phép restart Next dev: chỉ dừng hai process tree có command line trỏ tới `F:\web-app2\frontend`, giữ Uvicorn nguyên trạng; khởi động một Next dev server có tracked process `bgp_139bd2ed1001Mgk4q0vYI3nn62`.
- Sau restart: 7 routes (`/`, `/downloads`, filtered downloads, filtered gallery, `/jobs`, `/accounts`, `/settings`) đều HTTP 200; frontend log không có exception. Trang đầu compile 3.4s, các route sau 0.09–0.43s.
- Backend `/api/health`, downloads, jobs, accounts, settings đều HTTP 200.
- Test: backend pytest 9 passed (1 Pydantic deprecation warning); detector 12 checks pass; download-filter helper 3 checks pass; production build pass; type-check pass khi chạy tuần tự.
- Lần type-check ban đầu bị chạy song song với `next build` và báo thiếu `.next/types`; chạy lại tuần tự pass. Không phải lỗi ứng dụng.
- Docker Desktop engine báo running nhưng compose app containers ở `Created`, DB orphan stopped; compose hiện không định nghĩa service `postgres` nên không thể start bằng service name. Docker runtime chưa được xác minh; host backend/frontend hiện hoạt động.

### 2026-10-14 — Phase 0/1 follow-up

- `frontend/tailwind.config.ts`, `app/globals.css`: áp dụng token palette trong §4, semantic aliases tương thích UI đang có, focus ring và reduced-motion.
- `frontend/app/layout.tsx`, `components/Sidebar.tsx`, `components/BrandMark.tsx`: Inter Tight/Inter/JetBrains Mono, brand Dnload Social, app-shell identity.
- Added primitives: `PageHeader`, `EmptyState`, `PlatformDot`, `StatusDot`, `ShortcutChip`.
- `frontend/components/CommandPalette.tsx`, `CommandPaletteHost.tsx`, `lib/detect.ts`: palette global, Ctrl/⌘K, add nhanh từ URL, detect host/content type; URL profile không ép content type.
- `frontend/app/page.tsx`: quick-add horizontal pills, global action entry, resume/stop controls, queue summary 3 nền tảng, terminal height 360px.
- `frontend/app/gallery/page.tsx`: sửa tham số stream thành `path` theo API `useGalleryStream`.
- `frontend/lib/detect.test.ts`: 12 assertions pass cho IG post/profile/story, X, TikTok, host không hỗ trợ.
- Verification: `npm run type-check` pass; `npm run build` pass; dashboard API smoke through frontend proxy 6/6 HTTP 200.
- Chưa xác nhận browser-interaction của palette submit; chưa đánh dấu Phase 0/1 hoàn tất theo toàn bộ Definition of Done §13 cho tới khi visual/responsive/keyboard acceptance được chạy.

### 2026-10-14 — Phase 2 Downloads

- `frontend/app/downloads/page.tsx`: thêm Table/List view, shareable filter query (`q`, `platform`, `status`, `source`, `view`), restore browser navigation, infinite pagination / “Tải thêm”, Ctrl/Cmd-click selection, Shift-range, ArrowUp/Down row navigation, Space/Enter toggle và Esc clear.
- Route dùng `Suspense` + shimmer fallback để đáp ứng Next.js static prerender cho `useSearchParams`.
- Added `frontend/lib/download-filters.ts` và `download-filters.test.ts`; serialization, parsing và default view: 3 checks pass.
- Verification: `npm run type-check` pass; `npm run build` pass; `GET /api/downloads?page=1&page_size=50` HTTP 200.
- Docker runtime không thể deploy/verify: process Node Next.js của repo giữ port 3000 và Uvicorn giữ port 8000; user chọn giữ server host đang chạy, không dừng các process này. PostgreSQL container đang stopped. Không dùng `docker compose down`/không xóa volume.

## 10a. Quy ước cho lần sau (khi tiếp tục)

Khi vào phiên mới, đọc:
- Bảng trạng thái ở trên
- File mới nhất trong `frontend/app/` — Sidebar link nào trỏ tới route chưa tồn tại → đó là việc cần làm
- Component primitives ở `frontend/components/` — đã có thì dùng, không tạo mới
- `docs/REDESIGN-PLAN.md` §11 anti-patterns — không phạm

Tiêu chí "xong một phase" (Definition of Done §13):
- Match design system §4
- Không có anti-pattern §11
- `npx tsc --noEmit` pass
- EmptyState + loading skeleton có đủ
- Cập nhật bảng trạng thái ở §10 của file này

Tổng effort: ~2-3 tuần (1 người full-time). Có thể chia thành 6 PR, mỗi PR 1 phase.

## 11. Anti-patterns cần tránh

- ❌ Gradient tím → hồng → xanh (AI-cliché)
- ❌ Emoji làm icon — dùng Lucide
- ❌ `rounded-2xl` ở mọi card (max 14)
- ❌ Card có border-left màu accent (Tailwind era noise)
- ❌ Headline dùng Inter weight 400 (dùng Inter Tight 600)
- ❌ Bỏ focus ring để "đẹp hơn"
- ❌ 3+ saturated color cùng lúc trên 1 view
- ❌ Generic illustration / SVG-drawn mặt người
- ❌ Loading spinner xoay thay cho skeleton
- ❌ Toast spam nhiều cái một lúc
- ❌ Dùng platform brand color cho toàn bộ row (chỉ 1 dot 4px)

## 12. Tham chiếu

- Recipe chính: `.cursor/skills/web-design-engineer/references/style-recipes/linear.md`
- Recipe phụ: `.cursor/skills/web-design-engineer/references/style-recipes/raycast.md`
- Codebase hiện tại: `frontend/app/`, `frontend/components/`, `frontend/tailwind.config.ts`
- Backend API không thay đổi — chỉ redesign frontend
- Skill: `.cursor/skills/web-design-engineer/SKILL.md` (đọc lại trước khi bắt đầu mỗi phase)

## 13. Definition of Done (mỗi phase)

- [ ] Visual match với design system ở mục 4 (check bằng ảnh chụp)
- [ ] Không có anti-pattern ở mục 11
- [ ] `npx tsc --noEmit` pass
- [ ] Responsive ở 3 breakpoint (mobile / tablet / desktop)
- [ ] Keyboard nav cơ bản (Tab / Shift+Tab / Esc) hoạt động
- [ ] Không có font load chậm / layout shift
- [ ] Empty state + loading state đầy đủ
- [ ] Phase trước không bị regress (vẫn dùng được feature cũ)

---

> **Cập nhật:** khi bắt đầu mỗi phase, đọc lại skill `web-design-engineer/SKILL.md` (đặc biệt Step 0 verify facts, Step 2b calibration, Step 3 design system declaration) trước khi viết code. Plan này chỉ là tấm bản đồ, skill là la bàn.
