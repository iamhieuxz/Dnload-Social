"""One-off migration: create twitter_cookies table + content_type column on downloads.

Run from backend/ dir:
    .\.venv\Scripts\python.exe -m app.migrations.add_twitter_cookies
"""
import asyncio
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "igdownloader.db"


def main() -> None:
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        return
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # 1. content_type column on downloads
    cur.execute("PRAGMA table_info('downloads')")
    cols = {row[1] for row in cur.fetchall()}
    if "content_type" not in cols:
        cur.execute("ALTER TABLE downloads ADD COLUMN content_type VARCHAR(20)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_downloads_content_type ON downloads(content_type)")
        print("+ downloads.content_type added")
    else:
        print("= downloads.content_type already exists")

    # 2. twitter_cookies table
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='twitter_cookies'")
    if cur.fetchone() is None:
        cur.execute(
            """
            CREATE TABLE twitter_cookies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot VARCHAR(16) NOT NULL UNIQUE,
                file_name VARCHAR(255) NOT NULL,
                file_path VARCHAR(1024) NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_used_at DATETIME
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS ix_twitter_cookies_slot ON twitter_cookies(slot)")
        print("+ twitter_cookies table created")
    else:
        print("= twitter_cookies already exists")

    conn.commit()
    conn.close()
    print("Migration OK")


if __name__ == "__main__":
    main()
