"""add downloads table + job/account relationships (idempotent)

Revision ID: 0002_downloads
Revises: 0001_initial
Create Date: 2026-10-09 00:30:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_downloads"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if not _table_exists("downloads"):
        op.create_table(
            "downloads",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("job_id", sa.Integer, sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("platform", sa.String(16), nullable=False, index=True),
            sa.Column("source_type", sa.String(16), nullable=False, index=True),
            sa.Column("url", sa.String(2048), nullable=False, index=True),
            sa.Column("shortcode", sa.String(64), nullable=True, index=True),
            sa.Column("media_type", sa.String(20), nullable=True),
            sa.Column("title", sa.String(512), nullable=True),
            sa.Column("author", sa.String(255), nullable=True, index=True),
            sa.Column("file_path", sa.String(2048), nullable=True),
            sa.Column("file_name", sa.String(512), nullable=True),
            sa.Column("file_size_bytes", sa.Integer, nullable=False, server_default="0"),
            sa.Column("thumbnail_url", sa.String(2048), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending", index=True),
            sa.Column("error_message", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime, nullable=True),
        )
    if not _index_exists("downloads", "ix_downloads_status_created"):
        op.create_index("ix_downloads_status_created", "downloads", ["status", "created_at"])
    if not _index_exists("downloads", "ix_downloads_platform_created"):
        op.create_index("ix_downloads_platform_created", "downloads", ["platform", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_downloads_platform_created", table_name="downloads")
    op.drop_index("ix_downloads_status_created", table_name="downloads")
    op.drop_table("downloads")