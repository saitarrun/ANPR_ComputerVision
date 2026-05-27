"""Initial ANPR schema with 9 tables, constraints, and indexes.

Revision ID: 001
Revises: 
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa


revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all 9 tables with constraints and indexes."""

    # 1. regions table
    op.create_table(
        "regions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("regex_pattern", sa.Text(), nullable=False),
        sa.Column("charset_whitelist", sa.String(255), nullable=False),
        sa.Column("char_confusion_map", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_regions"),
        sa.UniqueConstraint("code", name="uq_region_code"),
    )
    op.create_index("ix_regions_code", "regions", ["code"])

    # 2. users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("updated_at", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint(
            "role IN ('viewer', 'operator', 'admin')",
            name="ck_users_role",
        ),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # 3. cameras table
    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stream_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False, server_default="rtsp"),
        sa.Column("rtsp_url", sa.Text(), nullable=True),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="inactive"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cameras"),
        sa.UniqueConstraint("stream_id", name="uq_cameras_stream_id"),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"], ondelete="RESTRICT", name="fk_cameras_region_id"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT", name="fk_cameras_created_by_user_id"),
    )
    op.create_index("ix_cameras_region_id", "cameras", ["region_id"])
    op.create_index("ix_cameras_created_by_user_id", "cameras", ["created_by_user_id"])
    op.create_index("ix_cameras_stream_id", "cameras", ["stream_id"])

    # 4. plates table
    op.create_table(
        "plates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plate_string_encrypted", sa.Text(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("detected_at", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("crop_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_plates"),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"], ondelete="RESTRICT", name="fk_plates_region_id"),
        sa.UniqueConstraint("plate_string_encrypted", "region_id", name="uq_plate_per_region"),
    )
    op.create_index("ix_plates_region_id_created_at", "plates", ["region_id", "created_at"])
    op.create_index("ix_plates_confidence", "plates", ["confidence"])

    # 5. detections table
    op.create_table(
        "detections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plate_id", sa.Integer(), nullable=False),
        sa.Column("frame_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("avg_confidence", sa.Float(), nullable=False),
        sa.Column("tracking_id", sa.String(50), nullable=True),
        sa.Column("stream_context", sa.Text(), nullable=True),
        sa.Column("camera_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_detections"),
        sa.ForeignKeyConstraint(["plate_id"], ["plates.id"], ondelete="CASCADE", name="fk_detections_plate_id"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE", name="fk_detections_camera_id"),
        sa.CheckConstraint(
            "avg_confidence >= 0 AND avg_confidence <= 1",
            name="ck_avg_confidence_range",
        ),
    )
    op.create_index("ix_detections_plate_id", "detections", ["plate_id"])
    op.create_index("ix_detections_camera_id_created_at", "detections", ["camera_id", "created_at"])
    op.create_index("ix_detections_tracking_id", "detections", ["tracking_id"])

    # 6. audit_log table (append-only)
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("ip_addr", sa.String(45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT", name="fk_audit_log_user_id"),
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    # 7. watchlist table
    op.create_table(
        "watchlist",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plate_pattern", sa.String(255), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.String(30), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_watchlist"),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"], ondelete="RESTRICT", name="fk_watchlist_region_id"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT", name="fk_watchlist_created_by_user_id"),
    )
    op.create_index("ix_watchlist_region_id", "watchlist", ["region_id"])
    op.create_index("ix_watchlist_created_by_user_id", "watchlist", ["created_by_user_id"])

    # 8. review_queue table
    op.create_table(
        "review_queue",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("detection_blob", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.String(30), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_queue"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL", name="fk_review_queue_reviewed_by_user_id"),
    )
    op.create_index("ix_review_queue_status", "review_queue", ["status"])
    op.create_index("ix_review_queue_reviewed_by_user_id", "review_queue", ["reviewed_by_user_id"])

    # 9. api_keys table
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("permissions", sa.Text(), nullable=False),
        sa.Column("last_used_at", sa.String(30), nullable=True),
        sa.Column("expired_at", sa.String(30), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_api_keys"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_api_keys_user_id"),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])


def downgrade() -> None:
    """Drop all tables in reverse order of creation."""
    op.drop_table("api_keys")
    op.drop_table("review_queue")
    op.drop_table("watchlist")
    op.drop_table("audit_log")
    op.drop_table("detections")
    op.drop_table("plates")
    op.drop_table("cameras")
    op.drop_table("users")
    op.drop_table("regions")
