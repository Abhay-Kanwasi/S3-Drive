"""
S3 Explorer user access — separate from UAM account status.

- UAM: user_data.active (read-only here; UAM owns writes)
- S3 Explorer admin deactivate: s3_user_deactivation row only
- Auth checks both on every request (same DB, no polling)
"""

from datetime import datetime, timezone
from typing import Iterable, Optional, Set

from sqlalchemy.orm import Session

from db.models import S3UserDeactivation


def s3_deactivated_user_ids(db: Session, user_ids: Iterable[int]) -> Set[int]:
    if not user_ids:
        return set()
    rows = (
        db.query(S3UserDeactivation.user_id)
        .filter(S3UserDeactivation.user_id.in_(list(user_ids)))
        .all()
    )
    return {r[0] for r in rows}


def is_s3_deactivated(db: Session, user_id: int) -> bool:
    return (
        db.query(S3UserDeactivation.user_id)
        .filter(S3UserDeactivation.user_id == user_id)
        .first()
        is not None
    )


def effective_s3_access(uam_active: Optional[bool], s3_deactivated: bool) -> bool:
    """True when the user may use S3 Explorer (UAM active and not S3-deactivated)."""
    return bool(uam_active) and not s3_deactivated


def get_s3_deactivated_at(db: Session, user_id: int) -> Optional[datetime]:
    row = (
        db.query(S3UserDeactivation)
        .filter(S3UserDeactivation.user_id == user_id)
        .first()
    )
    if row is None or row.deactivated_at is None:
        return None
    ts = row.deactivated_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def mark_s3_deactivated(db: Session, user_id: int, deactivated_by: int) -> datetime:
    """Stage deactivation row; caller must db.commit() after audit."""
    now = datetime.now(timezone.utc)
    existing = (
        db.query(S3UserDeactivation)
        .filter(S3UserDeactivation.user_id == user_id)
        .first()
    )
    if existing:
        existing.deactivated_at = now
        existing.deactivated_by = deactivated_by
    else:
        db.add(
            S3UserDeactivation(
                user_id=user_id,
                deactivated_at=now,
                deactivated_by=deactivated_by,
            )
        )
    db.flush()
    return now


def clear_s3_deactivation(db: Session, user_id: int) -> None:
    """Remove deactivation row; caller must db.commit() after audit."""
    db.query(S3UserDeactivation).filter(S3UserDeactivation.user_id == user_id).delete()
    db.flush()
