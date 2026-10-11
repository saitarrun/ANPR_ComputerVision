"""Privacy & retention Celery tasks (F13–F14)."""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from urllib.parse import urlparse

from celery import shared_task
from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
import yaml

from api.settings import settings
from db.core import Database
from db.models import Plate, AuditLog
from workers.s3_utils import s3_put_object

logger = logging.getLogger(__name__)

db = Database(settings.database_url)

# Load retention config
import os

config_path = os.path.join(os.path.dirname(__file__), "../config/retention.yaml")
with open(config_path, "r") as f:
    retention_config = yaml.safe_load(f)


@shared_task(name="privacy.purge_expired_plates", bind=True)  # type: ignore[untyped-decorator]
def purge_expired_plates(self: Any) -> dict[str, Any]:
    """Delete plates older than retention window."""
    deleted_counts = {}
    try:
        import asyncio

        deleted_counts = asyncio.run(_purge_expired_async())
    except Exception as e:
        logger.error(f"Purge task failed: {e}", exc_info=True)
    return deleted_counts


async def _purge_expired_async() -> dict[str, Any]:
    """Async purge implementation."""
    deleted_counts = {}
    async with db.get_session() as session:
        for region, policy in retention_config["retention_policies"].items():
            retention_days = policy["retention_days"]
            cutoff_ts = datetime.now(timezone.utc) - timedelta(days=retention_days)

            delete_stmt = delete(Plate).where(
                (Plate.region_id == region) & (Plate.created_at < cutoff_ts)
            )
            delete_result = cast("CursorResult[Any]", await session.execute(delete_stmt))
            await session.commit()

            deleted_counts[region] = int(delete_result.rowcount or 0)
            logger.info(f"Purged {deleted_counts[region]} plates from {region}")

    return deleted_counts


@shared_task(name="privacy.archive_audit_log", bind=True)  # type: ignore[untyped-decorator]
def archive_audit_log(self: Any) -> dict[str, Any]:
    """Export audit logs to S3 daily with tamper-detection."""
    try:
        import asyncio

        return asyncio.run(_archive_audit_async())
    except Exception as e:
        logger.error(f"Archive task failed: {e}", exc_info=True)
        return {"s3_key": "", "rows": 0, "error": str(e)}


async def _archive_audit_async() -> dict[str, Any]:
    """Async audit log archival implementation."""
    async with db.get_session() as session:
        archive_age_days = 7
        cutoff_ts = datetime.now(timezone.utc) - timedelta(days=archive_age_days)

        stmt = select(AuditLog).where(AuditLog.ts < cutoff_ts).order_by(AuditLog.ts)
        result = await session.execute(stmt)
        logs = result.scalars().all()

        if not logs:
            logger.info("No audit logs to archive")
            return {"s3_key": "", "rows": 0}

        # Serialize to JSONL
        lines = []
        for log in logs:
            lines.append(
                json.dumps(
                    {
                        "id": log.id,
                        "user_id": log.user_id,
                        "action": log.action,
                        "resource_type": log.resource_type,
                        "resource_id": log.resource_id,
                        "ts": log.ts.isoformat() if log.ts else None,
                        "ip_addr": log.ip_addr,
                        "justification": log.justification,
                    }
                )
            )

        content = "\n".join(lines)
        content_bytes = content.encode("utf-8")

        # Compute SHA256 signature
        signature = hashlib.sha256(content_bytes).hexdigest()

        # Upload to S3
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        s3_key = f"audit-backups/audit_log_{date_str}.jsonl"

        success = s3_put_object(
            key=s3_key,
            body=content_bytes,
            metadata={
                "signature": signature,
                "row_count": str(len(logs)),
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )

        if success:
            logger.info(f"Archived {len(logs)} audit logs to {s3_key}")
        else:
            logger.error(f"Failed to upload archive to {s3_key}")

        return {
            "s3_key": s3_key,
            "signature": f"sha256:{signature}",
            "rows": len(logs),
        }
