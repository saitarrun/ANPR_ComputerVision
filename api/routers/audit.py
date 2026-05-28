"""Audit log endpoints for compliance and audit trails."""

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from datetime import datetime, timedelta
import io
import csv
import logging

from api.deps import get_db_session, get_current_user_id
from db.models import AuditLog
from api.schemas.data import AuditLogOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/audit-log", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
async def list_audit_log(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    user_id_filter: str | None = Query(None),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """List audit log entries with optional filters.

    Args:
        date_from: Filter from date (ISO 8601)
        date_to: Filter to date (ISO 8601)
        user_id_filter: Filter by user ID
        action: Filter by action type
        resource_type: Filter by resource type
        limit: Maximum entries to return
        db: Database session
        user_id: Current user ID (for access control)

    Returns:
        List of audit log entries
    """
    conditions = []

    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            conditions.append(AuditLog.created_at >= dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            conditions.append(AuditLog.created_at <= dt_to)
        except ValueError:
            pass

    if user_id_filter:
        conditions.append(AuditLog.user_id == user_id_filter)

    if action:
        conditions.append(AuditLog.action == action)

    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)

    stmt = select(AuditLog)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(desc(AuditLog.created_at)).limit(limit)
    result = await db.execute(stmt)
    entries = result.scalars().all()

    return [
        AuditLogOut(
            id=str(e.id),
            user_id=str(e.user_id),
            action=e.action,
            resource_type=e.resource_type,
            resource_id=str(e.resource_id),
            ip_address=e.ip_address,
            details=e.details,
            created_at=e.created_at,
        )
        for e in entries
    ]


@router.get("/export/csv")
async def export_audit_log_csv(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    user_id_filter: str | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """Export audit log to CSV for compliance.

    Args:
        date_from: Filter from date (ISO 8601)
        date_to: Filter to date (ISO 8601)
        user_id_filter: Filter by user ID
        db: Database session
        user_id: Current user ID (for access control)

    Returns:
        CSV file stream
    """
    conditions = []

    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            conditions.append(AuditLog.created_at >= dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            conditions.append(AuditLog.created_at <= dt_to)
        except ValueError:
            pass

    if user_id_filter:
        conditions.append(AuditLog.user_id == user_id_filter)

    stmt = select(AuditLog)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(desc(AuditLog.created_at))
    result = await db.execute(stmt)
    entries = result.scalars().all()

    # Generate CSV
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "timestamp",
            "user_id",
            "action",
            "resource_type",
            "resource_id",
            "ip_address",
            "details",
        ],
    )

    writer.writeheader()
    for entry in entries:
        writer.writerow({
            "timestamp": entry.created_at.isoformat(),
            "user_id": entry.user_id,
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "ip_address": entry.ip_address,
            "details": entry.details,
        })

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )
