"""
Cron job: Remove group memberships for users deactivated beyond the grace window.

Targets ONLY S3 Explorer tables:
  - s3_group_membership (removes rows for expired deactivated users)
  - s3_user_deactivation (reads deactivation timestamp)

Does NOT touch UAM tables (user_data, etc.) — UAM remains read-only.

Race-safe: uses a single DELETE ... WHERE user_id IN (subquery) so that if a user
is reactivated (their s3_user_deactivation row is removed) between the count and
delete, the subquery re-evaluates at execution time and skips them.

Schedule: run daily (e.g. via cron, Kubernetes CronJob, or ECS scheduled task).

Usage:
    python scripts/cleanup_deactivated_memberships.py [--dry-run] [--grace-days 30]
"""

import argparse
import logging
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from db.postgresdb import Session
from db.models import S3UserDeactivation, GroupMembership
from core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_GRACE_DAYS = settings.DEACTIVATION_GRACE_DAYS


def _expired_user_ids_subquery(cutoff):
    """Subquery returning user_ids with deactivation older than cutoff."""
    return (
        select(S3UserDeactivation.user_id)
        .where(S3UserDeactivation.deactivated_at < cutoff)
        .correlate(None)
        .scalar_subquery()
    )


def cleanup_expired_memberships(grace_days: int, dry_run: bool) -> dict:
    """
    Atomically delete group memberships for users whose s3_user_deactivation
    is older than `grace_days`. The subquery is evaluated at DELETE time,
    preventing races with concurrent reactivation.

    Returns {"memberships_removed": int}.
    """
    if grace_days < 1:
        raise ValueError("grace_days must be at least 1")

    db = Session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=grace_days)
        logger.info("Cutoff: %s (users deactivated before this lose memberships)", cutoff.isoformat())

        expired_subq = _expired_user_ids_subquery(cutoff)

        if dry_run:
            total = (
                db.query(GroupMembership)
                .filter(GroupMembership.user_id.in_(
                    select(S3UserDeactivation.user_id)
                    .where(S3UserDeactivation.deactivated_at < cutoff)
                ))
                .count()
            )
            if not total:
                logger.info("[DRY RUN] No stale memberships found. Nothing to do.")
                return {"memberships_removed": 0}

            preview = (
                db.query(GroupMembership)
                .filter(GroupMembership.user_id.in_(
                    select(S3UserDeactivation.user_id)
                    .where(S3UserDeactivation.deactivated_at < cutoff)
                ))
                .limit(20)
                .all()
            )
            logger.info("[DRY RUN] Would remove %d memberships. Sample:", total)
            for m in preview:
                logger.info("  user_id=%d, group_id=%d, added_at=%s", m.user_id, m.group_id, m.added_at)
            if total > 20:
                logger.info("  ... and %d more", total - 20)
            return {"memberships_removed": total}

        deleted = (
            db.query(GroupMembership)
            .filter(GroupMembership.user_id.in_(expired_subq))
            .delete(synchronize_session=False)
        )
        db.commit()

        if deleted:
            logger.info("Removed %d group memberships.", deleted)
        else:
            logger.info("No stale memberships found. Nothing to do.")

        return {"memberships_removed": deleted}

    except Exception:
        db.rollback()
        logger.exception("Cleanup failed — rolled back.")
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Remove group memberships for users deactivated beyond the grace window. Only affects s3_group_membership."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be deleted without making changes.",
    )
    parser.add_argument(
        "--grace-days",
        type=int,
        default=DEFAULT_GRACE_DAYS,
        help=f"Days after deactivation before memberships are purged (default: {DEFAULT_GRACE_DAYS}).",
    )
    args = parser.parse_args()

    if args.grace_days < 1:
        parser.error("--grace-days must be at least 1.")

    logger.info("=== S3 Explorer membership cleanup ===")
    logger.info("Grace period: %d days | Dry run: %s", args.grace_days, args.dry_run)

    result = cleanup_expired_memberships(grace_days=args.grace_days, dry_run=args.dry_run)

    logger.info(
        "Done. Memberships removed: %d",
        result["memberships_removed"],
    )


if __name__ == "__main__":
    main()
