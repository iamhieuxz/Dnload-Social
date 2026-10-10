#!/usr/bin/env bash
# ============================================================================
#  Instagram Downloader v7.0 — One-Click Launcher (macOS / Linux)
#  Chạy:  ./start.sh
#  Dừng:  ./stop.sh
# ============================================================================
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOGS_DIR="$ROOT/logs"
PIDS_DIR="$ROOT/.pids"
mkdir -p "$LOGS_DIR" "$PIDS_DIR"

# Colors
R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'; M='\033[0;35m'; N='\033[0m'

banner() {
    echo -e "${M}"
    echo "  ╔══════════════════════════════════════════════════════╗"
    echo "  ║   Instagram Downloader v7.0  —  One-Click Launcher    ║"
    echo "  ╚══════════════════════════════════════════════════════╝"
    echo -e "${N}"
}

# ---- Prereqs ----
banner
echo -e "  ${C}🔍 Kiểm tra môi trường...${N}"
MISSING=()
for c in python3 node docker; do
    if ! command -v $c &>/dev/null; then
        MISSING+=("$c")
    fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
    echo -e "  ${R}❌ Thiếu: ${MISSING[*]}${N}"
    echo "     Python 3.11+ → https://python.org"
    echo "     Node.js 20+  → https://nodejs.org"
    echo "     Docker       → https://docker.com"
    exit 1
fi
if ! docker info &>/dev/null; then
    echo -e "  ${R}❌ Docker chưa chạy (hãy mở Docker Desktop)${N}"
    exit 1
fi
echo -e "  ${G}✓ Python:  $(python3 --version)${N}"
echo -e "  ${G}✓ Node:    $(node --version)${N}"
echo -e "  ${G}✓ Docker:  $(docker --version)${N}"
echo

# ---- PostgreSQL ----
echo -e "  ${C}🐘 Khởi động PostgreSQL...${N}"
if docker ps --format '{{.Names}}' | grep -q '^ig-postgres$'; then
    echo -e "  ${G}✓ Container đang chạy${N}"
elif docker ps -a --format '{{.Names}}' | grep -q '^ig-postgres$'; then
    echo -e "  ${Y}▶ Start container...${N}"
    docker start ig-postgres >/dev/null
else
    echo -e "  ${Y}▶ Tạo container...${N}"
    docker run -d --name ig-postgres \
        -e POSTGRES_USER=iguser -e POSTGRES_PASSWORD=igpass -e POSTGRES_DB=igdownloader \
        -p 5432:5432 -v ig_pg_data:/var/lib/postgresql/data \
        postgres:16-alpine >/dev/null
fi
sleep 2
echo -e "  ${G}✓ PostgreSQL OK${N}"
echo

# ---- Backend env + venv ----
echo -e "  ${C}🐍 Chuẩn bị Backend...${N}"
[ -f "$ROOT/backend/.env" ] || cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"

if [ ! -d "$ROOT/backend/.venv" ]; then
    echo -e "  ${Y}▶ Tạo venv...${N}"
    python3 -m venv "$ROOT/backend/.venv"
fi

PY="$ROOT/backend/.venv/bin/python"
echo -e "  ${Y}▶ pip install...${N}"
"$PY" -m pip install --quiet --disable-pip-version-check -r "$ROOT/backend/requirements.txt"
echo -e "  ${G}✓ Backend deps OK${N}"
echo

# ---- Migrations ----
echo -e "  ${C}📦 Chạy migrations...${N}"
(cd "$ROOT/backend" && "$PY" -m alembic upgrade head)
echo -e "  ${G}✓ Schema OK${N}"
echo

# ---- Start backend ----
echo -e "  ${C}🚀 Khởi động Backend (port 8000)...${N}"
[ -f "$PIDS_DIR/backend.pid" ] && kill -9 $(cat "$PIDS_DIR/backend.pid") 2>/dev/null || true

nohup bash -c "cd '$ROOT/backend' && '$PY' -m uvicorn app.main:app --host 0.0.0.0 --port 8000" \
    > "$LOGS_DIR/backend.log" 2>&1 &
echo $! > "$PIDS_DIR/backend.pid"
echo -e "  ${G}✓ Backend PID: $(cat $PIDS_DIR/backend.pid)${N}"

# Wait for backend
for i in {1..30}; do
    if curl -s http://localhost:8000/api/health >/dev/null 2>&1; then
        echo -e "  ${G}✓ Backend ready${N}"
        break
    fi
    sleep 1
done
echo

# ---- Frontend ----
echo -e "  ${C}🌐 Chuẩn bị Frontend...${N}"
[ -d "$ROOT/frontend/node_modules" ] || {
    echo -e "  ${Y}▶ npm install (lần đầu mất 2-5 phút)...${N}"
    (cd "$ROOT/frontend" && npm install --no-audit --no-fund --loglevel=error)
}
echo -e "  ${G}✓ node_modules OK${N}"
echo

echo -e "  ${C}🚀 Khởi động Frontend (port 3000)...${N}"
[ -f "$PIDS_DIR/frontend.pid" ] && kill -9 $(cat "$PIDS_DIR/frontend.pid") 2>/dev/null || true

nohup bash -c "cd '$ROOT/frontend' && npx next dev -p 3000" \
    > "$LOGS_DIR/frontend.log" 2>&1 &
echo $! > "$PIDS_DIR/frontend.pid"
echo -e "  ${G}✓ Frontend PID: $(cat $PIDS_DIR/frontend.pid)${N}"

# Wait for frontend
for i in {1..90}; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null | grep -q "200\|307"; then
        echo -e "  ${G}✓ Frontend ready${N}"
        break
    fi
    sleep 1
done
echo

# ---- Done ----
echo -e "  ${M}═══════════════════════════════════════════════════════${N}"
echo -e "   ${G}✨  HỆ THỐNG ĐÃ SẴN SÀNG ✨${N}"
echo -e "  ${M}═══════════════════════════════════════════════════════${N}"
echo
echo -e "   ${N}Web UI:       ${C}http://localhost:3000${N}"
echo -e "   ${N}Backend API:  ${C}http://localhost:8000/docs${N}"
echo -e "   ${N}PostgreSQL:   ${C}localhost:5432  (iguser/igpass/igdownloader)${N}"
echo
echo -e "   ${N}Logs:         ${C}./logs/backend.log  &  ./logs/frontend.log${N}"
echo -e "   ${N}Dừng:         ${C}./stop.sh   (hoặc Ctrl+C ở đây)${N}"
echo

# Open browser
sleep 1
URL="http://localhost:3000"
if command -v xdg-open &>/dev/null; then xdg-open "$URL"
elif command -v open &>/dev/null; then open "$URL"
fi

# Wait + cleanup
trap 'echo -e "\n  ${Y}🛑 Đang dừng...${N}"; \
      [ -f "$PIDS_DIR/backend.pid" ] && kill -9 $(cat "$PIDS_DIR/backend.pid") 2>/dev/null; \
      [ -f "$PIDS_DIR/frontend.pid" ] && kill -9 $(cat "$PIDS_DIR/frontend.pid") 2>/dev/null; \
      echo -e "  ${G}✓ Đã dừng. Tạm biệt!${N}"; exit 0' INT TERM

echo -e "   ${Y}👀 Script đang chạy. Ctrl+C để dừng...${N}"
while true; do sleep 1; done
