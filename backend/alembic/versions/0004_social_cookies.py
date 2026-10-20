"""add twitter_cookies + tiktok_cookies tables (idempotent)

Revision ID: 0004_social_cookies
Revises: 0003_download_content_type
Create Date: 2026-10-13
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_social_cookies"
down_revision: Union[str, None] = "0003_download_content_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("twitter_cookies"):
        op.create_table(
            "twitter_cookies",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("slot", sa.String(16), nullable=False, unique=True),
            sa.Column("file_name", sa.String(255), nullable=False),
            sa.Column("file_path", sa.String(1024), nullable=False),
            sa.Column("size_bytes", sa.Integer, nullable=False, server_default="0"),
            sa.Column("uploaded_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column("last_used_at", sa.DateTime, nullable=True),
        )
        op.create_index("ix_twitter_cookies_slot", "twitter_cookies", ["slot"], unique=True)

    if not _table_exists("tiktok_cookies"):
        op.create_table(
            "tiktok_cookies",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("slot", sa.String(16), nullable=False, unique=True),
            sa.Column("file_name", sa.String(255), nullable=False),
            sa.Column("file_path", sa.String(1024), nullable=False),
            sa.Column("size_bytes", sa.Integer, nullable=False, server_default="0"),
            sa.Column("uploaded_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column("last_used_at", sa.DateTime, nullable=True),
        )
        op.create_index("ix_tiktok_cookies_slot", "tiktok_cookies", ["slot"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_tiktok_cookies_slot", table_name="tiktok_cookies")
    op.drop_table("tiktok_cookies")
    op.drop_index("ix_twitter_cookies_slot", table_name="twitter_cookies")
    op.drop_table("twitter_cookies")