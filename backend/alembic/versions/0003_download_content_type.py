"""add content_type to downloads (idempotent)

Revision ID: 0003_download_content_type
Revises: 0002_downloads
Create Date: 2026-10-13
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_download_content_type"
down_revision: Union[str, None] = "0002_downloads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if not _column_exists("downloads", "content_type"):
        op.add_column("downloads", sa.Column("content_type", sa.String(20), nullable=True))
    if not _index_exists("downloads", "ix_downloads_content_type"):
        op.create_index("ix_downloads_content_type", "downloads", ["content_type"])


def downgrade() -> None:
    op.drop_index("ix_downloads_content_type", table_name="downloads")
    op.drop_column("downloads", "content_type")