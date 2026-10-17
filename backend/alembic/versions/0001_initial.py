"""initial schema (idempotent)

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-08 23:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial"
down_revision: Union[str, None] = None
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
    if not _table_exists("accounts"):
        op.create_table(
            "accounts",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("username", sa.String(255), unique=True, nullable=False, index=True),
            sa.Column("destination_folder", sa.String(1024), nullable=False),
            sa.Column("first_scanned_at", sa.DateTime, nullable=True),
            sa.Column("last_scanned_at", sa.DateTime, nullable=True),
            sa.Column("total_posts", sa.Integer, nullable=False, server_default="0"),
            sa.Column("total_stories", sa.Integer, nullable=False, server_default="0"),
            sa.Column("total_highlights", sa.Integer, nullable=False, server_default="0"),
            sa.Column("total_size_bytes", sa.Integer, nullable=False, server_default="0"),
            sa.Column("is_dead", sa.Boolean, nullable=False, server_default=sa.text("false"), index=True),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        )

    if not _table_exists("jobs"):
        op.create_table(
            "jobs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("job_type", sa.Enum("add_new", "update_list", "update_all", "single", name="jobtype", native_enum=False, length=32), nullable=False, index=True),
            sa.Column("targets", sa.Text, nullable=True),
            sa.Column("include_posts", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("include_stories", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("include_highlights", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("disable_range", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("status", sa.Enum("queued", "running", "completed", "stopped", "failed", name="jobstatus", native_enum=False, length=32), nullable=False, index=True),
            sa.Column("started_at", sa.DateTime, nullable=True),
            sa.Column("finished_at", sa.DateTime, nullable=True),
            sa.Column("new_files_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("total_processed", sa.Integer, nullable=False, server_default="0"),
            sa.Column("error_message", sa.Text, nullable=True),
            sa.Column("log_output", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        )

    if not _table_exists("media"):
        op.create_table(
            "media",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("media_type", sa.String(20), nullable=False, index=True),
            sa.Column("file_path", sa.String(2048), nullable=False),
            sa.Column("file_name", sa.String(512), nullable=False),
            sa.Column("shortcode", sa.String(64), nullable=True, index=True),
            sa.Column("instagram_date", sa.Date, nullable=True, index=True),
            sa.Column("file_size_bytes", sa.Integer, nullable=False, server_default="0"),
            sa.Column("file_hash", sa.String(64), nullable=True, index=True),
            sa.Column("downloaded_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("file_path", name="uq_media_file_path"),
        )

    if not _table_exists("rate_limit_events"):
        op.create_table(
            "rate_limit_events",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("job_id", sa.Integer, sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("cookie_used", sa.String(255), nullable=True),
            sa.Column("keywords_matched", sa.Text, nullable=True),
            sa.Column("source_line", sa.Text, nullable=True),
            sa.Column("detected_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        )

    if not _table_exists("settings"):
        op.create_table(
            "settings",
            sa.Column("key", sa.String(128), primary_key=True),
            sa.Column("value", sa.Text, nullable=False),
            sa.Column("description", sa.String(512), nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("rate_limit_events")
    op.drop_table("media")
    op.drop_table("jobs")
    op.drop_table("accounts")
    op.drop_table("settings")