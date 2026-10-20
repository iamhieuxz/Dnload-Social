# Hướng dẫn mở Backend & Frontend

Tài liệu ngắn gọn — chỉ phần **khởi chạy dự án** sau khi đã cài đặt lần đầu.

> Cài đặt lần đầu (venv, `pip install`, `npm install`, `alembic upgrade head`, `.env`) xem [README.md](../README.md#cài-đặt-nhanh-sqlite--không-cần-docker).

---

## Mở 1 lần sau khi cài

Cần **2 cửa sổ PowerShell riêng** — 1 cho backend, 1 cho frontend.

### Cửa sổ 1 — Backend (port 8000)

```powershell
cd f:\web-app2\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Bạn sẽ thấy:

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

Backend OK khi mở <http://localhost:8000/api/health> trả về `{"status":"ok"}`.

### Cửa sổ 2 — Frontend (port 3000)

```powershell
cd f:\web-app2\frontend
npx next dev -p 3000
```

Bạn sẽ thấy:

```
- Local:        http://localhost:3000
- Network:      http://192.168.x.x:3000

✓ Ready in 2.3s
```

Mở <http://localhost:3000> trong trình duyệt — đó là giao diện chính.

---

## Đường dẫn nhanh

| | URL |
|---|---|
| **Web UI** | <http://localhost:3000> |
| **API docs (Swagger)** | <http://localhost:8000/docs> |
| **API health** | <http://localhost:8000/api/health> |

---

## Dừng

Nhấn `Ctrl+C` ở mỗi cửa sổ đang chạy.

Nếu port vẫn bị chiếm sau khi thoát, ép kill:

```powershell
Get-NetTCPConnection -LocalPort 8000,3000 -State Listen |
  ForEach-Object { taskkill /F /T /PID $_.OwningProcess }
```

---

## Khởi động lại nhanh (mỗi ngày)

Nếu ngày hôm trước đã cài xong, hôm nay chỉ cần mở 2 terminal rồi chạy lại 2 lệnh trên. Không cần `pip install` / `npm install` lại trừ khi `requirements.txt` hoặc `package.json` đổi.

---

## Lỗi thường gặp khi mở

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `ModuleNotFoundError: No module named 'fastapi'` | Quên kích hoạt venv hoặc chưa `pip install` | Chạy lại bước 1 của README. |
| `Address already in use` (port 8000/3000) | Cửa sổ cũ chưa thoát hẳn | Chạy lệnh `taskkill` ở trên, rồi mở lại. |
| Frontend báo "Failed to fetch" | Backend chưa chạy | Mở cửa sổ 1 trước, đợi backend ready, rồi mở frontend. |
| Frontend gọi sai port backend | Backend chạy port khác 8000 | Tạo/sửa `frontend/.env.local`: `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`, rồi restart frontend. |
| `alembic` lỗi khi chạy migration lần đầu | Chưa tạo `.env` hoặc thiếu `database_url` | Copy `.env.example` thành `.env`, điền `database_url`. |

---

## Chạy bằng Docker (tuỳ chọn, thay thế 2 cửa sổ trên)

```bash
cd f:\web-app2
docker compose up --build
```

Chỉ 1 cửa sổ — Docker tự mở cả backend + frontend. Truy cập <http://localhost:3000>.
