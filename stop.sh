#!/usr/bin/env bash
# Dừng tất cả service của Instagram Downloader
ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDS_DIR="$ROOT/.pids"

echo
echo "  🛑 Đang dừng tất cả service..."

# Kill via PID files
for f in "$PIDS_DIR"/*.pid; do
    [ -f "$f" ] || continue
    p=$(cat "$f")
    [ -n "$p" ] && kill -9 "$p" 2>/dev/null
    rm -f "$f"
done

# Kill anything still listening on our ports
for port in 3000 8000 5432; do
    pids=$(lsof -ti :$port 2>/dev/null)
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null
done

read -p "  Dừng luôn PostgreSQL container? (y/N): " STOP_PG
if [[ "$STOP_PG" =~ ^[Yy]$ ]]; then
    docker stop ig-postgres 2>/dev/null
    echo "  ✓ Đã dừng ig-postgres"
fi

echo "  ✓ Xong!"
