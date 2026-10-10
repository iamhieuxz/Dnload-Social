# Instagram Downloader — Backend (FastAPI + PostgreSQL)

Local server that wraps `gallery-dl` and persists all downloaded media
metadata into PostgreSQL. Designed to be paired with the Next.js frontend
in `../frontend`.

## Highlights vs. original Tkinter app

- Async I/O — UI never blocks
- One job at a time (no corrupted `.instagram_download_archive.sqlite`)
- Process kill by PID (not by image name) — safe to run alongside other tools
- Per-job log buffer + WebSocket broadcast for real-time UI updates
- Full media index in PostgreSQL — query, search, filter, stats

## Quick start (local Python)

```bash
# 1. Set up PostgreSQL (use Docker if you don't have it locally)
docker run --name ig-pg -e POSTGRES_PASSWORD=igpass -e POSTGRES_USER=iguser \
  -e POSTGRES_DB=igdownloader -p 5432:5432 -d postgres:16

# 2. Install Python deps
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# or: source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env to point DOWNLOAD_FOLDER to where you want files stored

# 4. Run migrations
alembic upgrade head

# 5. Start the server
uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000/docs> for the interactive Swagger UI.

## Configuration

All settings come from environment variables (see `.env.example`).
Most importantly:

| Var | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `DOWNLOAD_FOLDER` | Where gallery-dl writes files |
| `COOKIE_FOLDER` | Where cookie1.txt / cookie2.txt live |
| `RATE_LIMIT_*` | Tunable rate-limit policy |

## API

- `GET  /api/health`
- `GET  /api/stats/overview`
- `GET  /api/accounts?page=1&page_size=20&search=foo`
- `GET  /api/accounts/{id}`
- `PATCH /api/accounts/{id}`
- `POST /api/accounts/{id}/rescan`
- `DELETE /api/accounts/{id}`
- `GET  /api/media?account_id=&media_type=post&page=1`
- `GET  /api/media/{id}/file`
- `DELETE /api/media/{id}?delete_file=true`
- `POST /api/jobs` — create a job
- `GET  /api/jobs/active`
- `POST /api/jobs/{id}/stop`
- `GET  /api/jobs/{id}/logs`
- `GET  /api/settings`
- `POST /api/cookies/upload/{1|2}` (multipart)
- `WS   /ws/jobs/{id}` — live log stream
- `WS   /ws/system` — system events

## Development

```bash
ruff check app/         # linter
ruff format app/        # formatter
mypy app/               # type check
pytest                  # tests (none yet)
```
