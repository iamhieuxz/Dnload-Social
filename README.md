# Dnload Social

Download manager cho **Instagram · Twitter/X · TikTok** — chạy local, giao diện web, hàng đợi tải bền vững.

Paste link (một hoặc hàng trăm), hệ thống tải về đúng thư mục, ghi log thời gian thực, và **dừng giữa chừng rồi tiếp tục được** nhờ archive của gallery-dl.

> 🚀 **Mới cài lần đầu?** Bắt đầu ở [Cài đặt nhanh](#cài-đặt-nhanh-sqlite--không-cần-docker).
> ⚡ **Đã cài rồi, muốn mở lại?** Đọc [`docs/RUN.md`](docs/RUN.md) — chỉ 2 lệnh, 30 giây.

![Next.js](https://img.shields.io/badge/Next.js-15-black?style=flat-square&logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?style=flat-square&logo=fastapi)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## Mục lục

- [Tính năng](#tính-năng)
- [Cách hoạt động](#cách-hoạt-động)
- [Yêu cầu](#yêu-cầu)
- [Cài đặt nhanh (SQLite — không cần Docker)](#cài-đặt-nhanh-sqlite--không-cần-docker)
  - [📄 Hướng dẫn mở FE & BE hàng ngày](docs/RUN.md)
- [Cài đặt với Docker](#cài-đặt-với-docker)
- [Cấu hình](#cấu-hình)
- [Hướng dẫn sử dụng](#hướng-dẫn-sử-dụng)
- [Cấu trúc thư mục lưu trữ](#cấu-trúc-thư-mục-lưu-trữ)
- [Kiến trúc dự án](#kiến-trúc-dự-án)
- [API](#api)
- [Khắc phục sự cố](#khắc-phục-sự-cố)
- [Bảo mật](#bảo-mật)
- [Đóng góp](#đóng-góp)
- [Giấy phép](#giấy-phép)
- [Tác giả](#tác-giả)

---

## Tính năng

### Đa nền tảng

| Nền tảng | Engine | Nội dung hỗ trợ |
|---|---|---|
| **Instagram** | gallery-dl | Posts · Stories 24h · Highlights · Reels · Single post |
| **Twitter / X** | yt-dlp | Tweet · Video · Space đã kết thúc · Live broadcast đã kết thúc |
| **TikTok** | gallery-dl | Feed của user · Single video · Short link `vm.tiktok.com` |

- **Nhiều nguồn:** một link, danh sách hàng trăm link, hoặc chọn từ database.
- **Cả 3 nền tảng trong một UI**, có bộ lọc, tìm kiếm, xem lịch sử tải.

### Quản lý tải

- **Hàng đợi bền vững** — mọi link lưu vào database, không mất khi restart.
- **Stop & Resume** — dừng giữa chừng không mất tiến độ: archive sqlite của gallery-dl/yt-dlp ghi những gì đã tải, lần sau bỏ qua ngay.
- **Resume theo từng nền tảng** — badge hiển thị số pending / in-flight / resumable riêng cho IG, X, TikTok.
- **Fallback cookie** — khi cookie chính bị rate-limit (429), tự chuyển sang cookie dự phòng và dừng ngay cookie bị chặn.
- **Log thời gian thực** qua WebSocket, lọc theo mức độ (info / success / warn / error).

### Quản lý thư viện

- Duyệt cây thư mục dạng cây, **tìm kiếm toàn bộ file**, xem thống kê dung lượng.
- Xem trước ảnh / video trực tiếp, đổi tên, xoá.
- Giao diện tiếng Việt, dark mode, responsive.

### An toàn

- **Chỉ kill PID của tiến trình mình sinh ra** — không đụng tới `gallery-dl.exe` / `yt-dlp.exe` khác đang chạy trên máy.
- **Một job tại một thời điểm** (async lock) — tránh hỏng archive khi chạy song song.
- Cookie mã hoá Fernet khi lưu, `.env` và cookie **không bao giờ** commit lên git.

---

## Cách hoạt động

```
┌─────────────┐     HTTP/WebSocket      ┌──────────────┐
│  Next.js 15 │ ◄─────────────────────► │ FastAPI      │
│  (web UI)   │                         │  + SQLAlchemy│
└─────────────┘                         └──────┬───────┘
                                               │
                                    ┌──────────▼───────────┐
                                    │     JobRunner        │
                                    │  (1 job / lock duy   │
                                    │   nhất, theo platform)│
                                    └──────────┬───────────┘
                          ┌────────────────────┼────────────────────┐
                          ▼                    ▼                    ▼
                 ┌────────────────┐  ┌────────────────┐   ┌──────────────┐
                 │ InstagramService│ │ TwitterService │   │TikTokService │
                 │   (gallery-dl)  │ │   (yt-dlp)     │   │ (gallery-dl) │
                 └────────────────┘  └────────────────┘   └──────────────┘
                          └────────────────────┼────────────────────┘
                                               ▼
                                   ┌───────────────────────┐
                                   │  E:/gallery-dl/<nền tảng>/ │
                                   │        <user>/         │
                                   └───────────────────────┘
```

**Luồng chạy một link:**

1. Bạn paste link ở Dashboard → `POST /api/downloads/batch` tạo row `status=pending`.
2. Bấm **Run pending** → tạo `Job`, gắn các row vào job, chuyển sang `downloading`.
3. `JobRunner` khóa async lock, chọn đúng service theo platform, chạy subprocess.
4. Service đọc stdout từng dòng, nhận diện file mới → ghi `file_path` + size vào DB.
5. Job xong → `completed` / `failed` / `stopped`, phát WebSocket cho UI.

---

## Yêu cầu

| Thành phần | Phiên bản | Ghi chú |
|---|---|---|
| **Python** | 3.10+ | Chạy backend |
| **Node.js** | 18+ | Chạy frontend |
| **gallery-dl** | 1.30+ | Tự cài qua `pip install -r requirements.txt` |
| **yt-dlp** | bất kỳ | Tự cài qua `pip install -r requirements.txt` |
| **Dung lượng ổ đĩa | tuỳ video | Video TikTok ~5–50 MB mỗi cái |

> **Docker (không bắt buộc)** — nếu chỉ dùng SQLite thì không cần Docker.

---

## Cài đặt nhanh (SQLite — không cần Docker)

> 💡 **Sau khi cài xong, mỗi ngày chỉ cần 2 lệnh để chạy** — xem [`docs/RUN.md`](docs/RUN.md) (hướng dẫn ngắn, không cần đọc lại toàn bộ file này).

### 1. Tạo môi trường + cài backend

```powershell
cd f:\web-app2\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> macOS / Linux: `python3 -m venv .venv && source .venv/bin/activate`

### 2. Tạo file cấu hình

```powershell
cd f:\web-app2\backend
copy .env.example .env
```

Mở `.env` và sửa ít nhất 3 dòng đường dẫn lưu file cho đúng máy bạn:

```ini
download_folder=E:/gallery-dl/instagram
twitter_download_folder=E:/gallery-dl/twitter
tiktok_download_folder=E:/gallery-dl/tiktok
```

Sinh khoá mã hoá cookie (tuỳ chọn nhưng nên có):

```powershell
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Dán kết quả vào `cookie_encryption_key=` trong `.env`.

### 3. Chạy migration

```powershell
cd f:\web-app2\backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

### 4. Cài frontend

```powershell
cd f:\web-app2\frontend
npm install
```

### 5. Chạy

Mở **2 cửa sổ PowerShell riêng biệt**:

**Cửa sổ 1 — Backend (port 8000):**
```powershell
cd f:\web-app2\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Cửa sổ 2 — Frontend (port 3000):**
```powershell
cd f:\web-app2\frontend
npx next dev -p 3000
```

### 6. Truy cập

| | URL |
|---|---|
| **Web UI** | <http://localhost:3000> |
| **API docs** | <http://localhost:8000/docs> |
| **Health check** | <http://localhost:8000/api/health> |

### Dừng

Nhấn `Ctrl+C` ở mỗi cửa sổ, hoặc chạy:

```powershell
Get-NetTCPConnection -LocalPort 8000,3000 -State Listen |
  ForEach-Object { taskkill /F /T /PID $_.OwningProcess }
```

---

## Cài đặt với Docker

```bash
git clone https://github.com/iamhieuxz/Dnload-Social.git
cd Dnload-Social
docker compose up --build
```

Mở <http://localhost:3000>.

---

## Cấu hình

Tất cả tuỳ chọn nằm trong `backend/.env` (xem `.env.example`):

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `database_url` | `sqlite+aiosqlite:///./data/igdownloader.db` | SQLite hoặc PostgreSQL |
| `download_folder` | `E:/gallery-dl/instagram` | Nơi lưu Instagram |
| `twitter_download_folder` | `E:/gallery-dl/twitter` | Nơi lưu Twitter/X |
| `tiktok_download_folder` | `E:/gallery-dl/tiktok` | Nơi lưu TikTok |
| `cookie_folder` | `./secrets/cookies` | Nơi lưu file cookie |
| `cookie_encryption_key` | *(rỗng)* | Khoá Fernet — bắt buộc nếu muốn upload cookie |
| `rate_limit_min_delay` | `18` | Giây nghỉ tối thiểu giữa các request |
| `rate_limit_max_delay` | `45` | Giây nghỉ tối đa |
| `rate_limit_batch_size` | `8` | Số request trước khi nghỉ dài |
| `rate_limit_batch_cooldown` | `240` | Giây nghỉ dài sau một batch |
| `max_concurrent_jobs` | `1` | **Nên giữ = 1** để không hỏng archive |

---

## Hướng dẫn sử dụng

### 1. Nạp cookie (bắt buộc cho Instagram & Twitter/X)

Vào **Settings** → upload cookie:

- **Instagram:** lấy cookie từ trình duyệt bằng extension **Get cookies.txt LOCALLY**, upload vào ô *Cookie 1*. Upload thêm *Cookie 2* làm dự phòng.
- **Twitter/X:** upload file cookie Netscape tương tự.
- **TikTok:** **không cần cookie** — dữ liệu public đọc được khi chưa đăng nhập.

> Cookie là thông tin đăng nhập của bạn. Chỉ dùng cho tài khoản của chính bạn.

### 2. Thêm link và tải

Ở **Dashboard** → *Add to download queue*:

1. **Chọn nền tảng** — Instagram / Twitter / TikTok.
2. **Chọn nguồn** — *Single link*, *Bulk list*, hoặc *From database* (chỉ IG & X).
3. **Dán link** và bấm **Add to queue**.
4. Bấm **Run pending** để bắt đầu.

**Các dạng link TikTok được hỗ trợ:**

| Link | Kết quả |
|---|---|
| `https://www.tiktok.com/@username` | Toàn bộ feed video của user |
| `https://www.tiktok.com/@username/video/123` | Chỉ video đó |
| `vm.tiktok.com/ZMabc123/` | Short link → tự resolve |
| `@username` hoặc `username` | Tự chuẩn hoá thành profile URL |

**Chọn nhiều layer cho Instagram:** tích *Posts* / *Stories* / *Highlights* — mỗi layer tạo một row riêng, tải vào cùng thư mục user với tiền tố file khác nhau.

### 3. Theo dõi tiến trình

- **Live terminal** ở Dashboard hiển thị log thời gian thực.
- **Stop** dừng an toàn: tiến trình con bị kết thúc, các row đang chạy trả về `pending`.
- **Resume** chạy tiếp, tự bỏ qua file đã tải.

### 4. Xem lại kết quả

- **Downloads** — bảng chi tiết, lọc theo platform / trạng thái / nguồn, retry bản ghi lỗi.
- **Gallery** — duyệt cây thư mục, tìm kiếm, xem trước, đổi tên, xoá.
- **Jobs** — lịch sử từng lần chạy.

---

## Cấu trúc thư mục lưu trữ

```
E:/gallery-dl/
├── instagram/
│   └── <username>/
│       ├── 2026-10-01_ABC123_0001.jpg      ← post
│       ├── STORY_2026-10-01_DEF456_0001.jpg ← story 24h
│       ├── HL_2026-10-01_GHI789_0001.jpg    ← highlight
│       └── .instagram_download_archive.sqlite
├── twitter/
│   └── <username>/
│       ├── <uploader>_<id>_<timestamp>.mp4
│       └── .yt-dlp-archive.txt
└── tiktok/
    └── <username>/
        ├── 2026-10-01_7234567890.mp4
        └── .tiktok_download_archive.sqlite
```

File archive (dotfile) là **bộ nhớ** của tiến trình: nó ghi lại những gì đã tải, nên nếu xoá file này thì lần chạy sau sẽ tải lại từ đầu.

---

## Kiến trúc dự án

```
Dnload-Social/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routers (downloads, gallery, jobs, cookies...)
│   │   ├── core/          # process manager, rate limit, WebSocket, logging
│   │   ├── models/        # SQLAlchemy models (Download, Job, Account)
│   │   ├── schemas/       # Pydantic schemas
│   │   ├── services/      # Business logic: instagram.py, twitter.py, tiktok.py, job_runner.py
│   │   ├── alembic/       # Database migrations
│   │   ├── config.py      # Settings từ .env
│   │   └── main.py        # FastAPI app entry
│   └── requirements.txt
├── frontend/
│   ├── app/               # Next.js App Router (page, downloads, gallery, jobs...)
│   ├── components/        # UI components dùng chung
│   ├── lib/               # axios client, WebSocket hook, utils
│   └── package.json
├── docker-compose.yml
├── LICENSE                # MIT
└── README.md
```

### Vài thiết kế đáng chú ý

- **`JobRunner` giữ service theo dict** `{platform: service}` — thêm nền tảng mới là sửa một dòng, không phải nhân bản mọi nhánh `if/else`.
- **`TikTokService` kế thừa `InstagramService`** vì cùng engine gallery-dl; chỉ override 3 hook: URL normalize, thư mục đích, template tên file. Không copy-paste 500 dòng.
- **`AsyncProcessRunner` chỉ kill PID của mình** — an toàn với các tiến trình tải khác trên cùng máy.
- **Stop = mềm**: lập cờ `_stop_requested` + hạ subprocess, để generator không kẹt ở `await stdout.readline()`.

---

## API

Tài liệu tương tác đầy đủ: <http://localhost:8000/docs>

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/api/health` | Kiểm tra server |
| `POST` | `/api/downloads/batch` | Thêm nhiều link vào hàng đợi |
| `POST` | `/api/downloads/run-pending?platform=` | Chạy các row `pending` của một nền tảng |
| `GET` | `/api/downloads/pending-summary?platform=` | Đếm pending / in-flight / resumable |
| `GET` | `/api/downloads` | Danh sách + lọc + phân trang |
| `POST` | `/api/downloads/{id}/retry` | Đưa row lỗi về `pending` |
| `GET` | `/api/jobs/active` | Job đang chạy hiện tại |
| `POST` | `/api/jobs/{id}/stop` | Dừng job (reset row về `pending`) |
| `GET` | `/api/gallery/tree` | Cây thư mục |
| `GET` | `/api/gallery/search?q=` | Tìm file theo tên |
| `WS` | `/ws/system` | Stream log + sự kiện thời gian thực |

### Ví dụ

```bash
# Thêm 2 link TikTok
curl -X POST http://localhost:8000/api/downloads/batch \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "tiktok",
    "source_type": "link",
    "items": [
      {"url": "https://www.tiktok.com/@username"},
      {"url": "https://www.tiktok.com/@username/video/7234567890"}
    ]
  }'

# Chạy
curl -X POST "http://localhost:8000/api/downloads/run-pending?platform=tiktok"
```

---

## Khắc phục sự cố

<details>
<summary><b>Không tải được gì, báo <code>No output file found</code></b></summary>

- **Instagram:** thiếu cookie hợp lệ → vào Settings upload lại cookie.
- **Cookie hết hạn:** thay cookie mới. Cookie Instagram thường hết hạn sau vài tuần.
- **Bị rate-limit (429):** job tự dừng, nghỉ `rate_limit_limit_cooldown` giây rồi thử lại — hoặc tăng `rate_limit_min_delay`.
</details>

<details>
<summary><b>TikTok báo <code>403 Forbidden</code></b></summary>

TikTok chặn IP tạm thời khi bạn tải quá nhanh. Cần:
1. Đợi vài phút rồi thử lại, **hoặc**
2. Dùng mạng/VPN khác, **hoặc**
3. Giảm tần suất: chạy từng user một, không bulk nhiều user cùng lúc.

> Lưu ý: danh sách video vẫn xem được, nhưng tải file sẽ 403 — đây là hạn chế của TikTok, không phải lỗi phần mềm.
</details>

<details>
<summary><b>Bấm Stop nhưng job không dừng ngay</b></summary>

Không phải lỗi — backend cố gắng cho tiến trình con tự thoát trong 2 giây. Nếu gallery-dl đang ngủ giữa hai request (rate-limit cooldown) thì cần thêm chút thời gian. Row sẽ tự trả về `pending` và bạn bấm Resume được.
</details>

<details>
<summary><b>Frontend báo lỗi kết nối API</b></summary>

- Backend chưa chạy? Kiểm tra <http://localhost:8000/api/health>.
- Đổi port backend? Sửa `NEXT_PUBLIC_API_BASE_URL` trong `frontend/.env.local` rồi restart frontend.
</details>

<details>
<summary><b>Chạy lại mà bị tải lại từ đầu</b></summary>

File archive (`.*.sqlite` / `.yt-dlp-archive.txt`) trong thư mục user đã bị xoá. Xoá nó là mất bộ nhớ — hãy giữ lại.
</details>

<details>
<summary><b>Port 8000 hoặc 3000 đã bị chiếm</b></summary>

```powershell
Get-NetTCPConnection -LocalPort 8000,3000 -State Listen |
  ForEach-Object { taskkill /F /T /PID $_.OwningProcess }
```
</details>

---

## Bảo mật

- ✅ `.env`, `cookies.txt`, `secrets/`, `*.db`, `*.sqlite` đã được loại khỏi git bằng `.gitignore`.
- ✅ Cookie được mã hoá Fernet khi lưu xuống đĩa.
- ✅ Server chỉ kill PID của tiến trình mình tạo — không ảnh hưởng tiến trình khác trên máy.
- ✅ API có kiểm tra path-traversal ở các endpoint đọc file.

### ⚠️ Trước khi public repo

- [ ] Kiểm tra `.env` **không** nằm trong git: `git ls-files | Select-String "\.env$"`
- [ ] Xoá cookie cũ nếu đã từng commit ở nhánh khác
- [ ] Dùng tài khoản phụ / tài khoản Instagram phụ nếu bạn không muốn gắn cookie chính
- [ ] Bật 2FA cho tài khoản nếu cookie chứa phiên đăng nhập

**Chỉ tải nội dung của chính bạn hoặc nơi bạn có quyền.** Việc sử dụng vi phạm điều khoản dịch vụ của nền tảng có thể khiến tài khoản bị khóa.

---

## Đóng góp

1. Fork repo
2. Tạo nhánh: `git checkout -b feature/ten-tinh-nang`
3. Commit: `git commit -m "mô tả thay đổi"`
4. Push và tạo Pull Request

Một số quy ước trong dự án:

- Comment bằng tiếng Việt hoặc tiếng Anh, ngắn gọn.
- Backend: docstring giải thích **tại sao**, không giải thích **cái gì**.
- Frontend: component hiện có dùng lại thay vì viết mới.
- Chạy `npx tsc --noEmit` trước khi mở PR.

---

## Giấy phép

MIT — xem file [LICENSE](LICENSE).

```
MIT License
Copyright (c) 2026 iamhieuxz
```

---

## Tác giả

**iamhieuxz** — <https://github.com/iamhieuxz>

- Đã xây dựng và duy trì dự án này.
- Cảm ơn các dự án mã nguồn mở làm nền tảng:
  - [gallery-dl](https://github.com/mikf/gallery-dl) — Instagram & TikTok
  - [yt-dlp](https://github.com/yt-dlp/yt-dlp) — Twitter/X
  - [FastAPI](https://github.com/fastapi/fastapi), [Next.js](https://github.com/vercel/next.js)

---

<div align="center">

**Dnload Social** — tải nhanh, quản lý gọn.

Made with ❤️ in Vietnam

</div>