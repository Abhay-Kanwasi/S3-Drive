"""
Tests for scripts/cleanup_deactivated_memberships.py

Verifies:
  1. Dry-run does not delete anything
  2. Old deactivation (>30 days) memberships get removed
  3. Recent deactivation (<30 days) memberships are kept
  4. s3_user_deactivation row itself remains after cleanup
  5. s3_folder_grant is NOT touched
  6. Race: if user is reactivated before DELETE executes, memberships survive
"""

from datetime import datetime, timedelta, timezone

import pytest

from db.models import S3UserDeactivation, GroupMembership, UserGroup, FolderGrant, Org


@pytest.fixture
def seed_deactivation_data(db):
    """Set up an org, a group, an expired user and a recent user with memberships."""
    org = Org(
        org_name="Cron Test Org",
        bucket_name="cron-test-bucket",
        subscription_id=999,
        onboarded_by=1,
    )
    db.add(org)
    db.flush()

    group = UserGroup(name="dp-cron-group", org_id=org.id, created_by=1)
    db.add(group)
    db.flush()

    expired_user_id = 9001
    recent_user_id = 9002

    db.add(S3UserDeactivation(
        user_id=expired_user_id,
        deactivated_at=datetime.now(timezone.utc) - timedelta(days=45),
        deactivated_by=1,
    ))
    db.add(S3UserDeactivation(
        user_id=recent_user_id,
        deactivated_at=datetime.now(timezone.utc) - timedelta(days=10),
        deactivated_by=1,
    ))

    db.add(GroupMembership(group_id=group.id, user_id=expired_user_id, added_by=1))
    db.add(GroupMembership(group_id=group.id, user_id=recent_user_id, added_by=1))

    grant = FolderGrant(
        group_id=group.id, org_id=org.id, prefix="test/", access_level="read", created_by=1
    )
    db.add(grant)
    db.commit()

    return {
        "org": org,
        "group": group,
        "expired_user_id": expired_user_id,
        "recent_user_id": recent_user_id,
        "grant": grant,
    }


def test_dry_run_does_not_delete(db, seed_deactivation_data, monkeypatch):
    """Dry run reports what would be deleted but does not remove rows."""
    from scripts.cleanup_deactivated_memberships import cleanup_expired_memberships

    monkeypatch.setattr("scripts.cleanup_deactivated_memberships.Session", lambda: db)

    result = cleanup_expired_memberships(grace_days=30, dry_run=True)

    assert result["memberships_removed"] >= 1
    assert "expired_users" not in result

    remaining = db.query(GroupMembership).filter(
        GroupMembership.user_id == seed_deactivation_data["expired_user_id"]
    ).count()
    assert remaining == 1, "Dry run should not delete memberships"


def test_expired_deactivation_removes_memberships(db, seed_deactivation_data, monkeypatch):
    """Memberships for users deactivated >30 days ago are removed."""
    from scripts.cleanup_deactivated_memberships import cleanup_expired_memberships

    monkeypatch.setattr("scripts.cleanup_deactivated_memberships.Session", lambda: db)

    result = cleanup_expired_memberships(grace_days=30, dry_run=False)

    assert result["memberships_removed"] >= 1

    expired_remaining = db.query(GroupMembership).filter(
        GroupMembership.user_id == seed_deactivation_data["expired_user_id"]
    ).count()
    assert expired_remaining == 0, "Expired user memberships should be deleted"


def test_function_level_grace_days_validation(db, monkeypatch):
    """cleanup_expired_memberships raises ValueError if grace_days < 1."""
    from scripts.cleanup_deactivated_memberships import cleanup_expired_memberships

    with pytest.raises(ValueError, match="at least 1"):
        cleanup_expired_memberships(grace_days=0, dry_run=False)


def test_recent_deactivation_keeps_memberships(db, seed_deactivation_data, monkeypatch):
    """Memberships for users deactivated <30 days ago are NOT removed."""
    from scripts.cleanup_deactivated_memberships import cleanup_expired_memberships

    monkeypatch.setattr("scripts.cleanup_deactivated_memberships.Session", lambda: db)

    cleanup_expired_memberships(grace_days=30, dry_run=False)

    recent_remaining = db.query(GroupMembership).filter(
        GroupMembership.user_id == seed_deactivation_data["recent_user_id"]
    ).count()
    assert recent_remaining == 1, "Recent deactivation memberships should be kept"


def test_deactivation_row_remains(db, seed_deactivation_data, monkeypatch):
    """s3_user_deactivation row itself is NOT deleted by cleanup."""
    from scripts.cleanup_deactivated_memberships import cleanup_expired_memberships

    monkeypatch.setattr("scripts.cleanup_deactivated_memberships.Session", lambda: db)

    cleanup_expired_memberships(grace_days=30, dry_run=False)

    row = db.query(S3UserDeactivation).filter(
        S3UserDeactivation.user_id == seed_deactivation_data["expired_user_id"]
    ).first()
    assert row is not None, "Deactivation row should remain after cleanup"


def test_folder_grants_not_touched(db, seed_deactivation_data, monkeypatch):
    """s3_folder_grant is NOT affected by the cleanup."""
    from scripts.cleanup_deactivated_memberships import cleanup_expired_memberships

    grant_id = seed_deactivation_data["grant"].id
    group_id = seed_deactivation_data["group"].id

    monkeypatch.setattr("scripts.cleanup_deactivated_memberships.Session", lambda: db)

    cleanup_expired_memberships(grace_days=30, dry_run=False)

    grant = db.query(FolderGrant).filter(FolderGrant.id == grant_id).first()
    assert grant is not None, "Folder grants should not be touched"


def test_reactivated_user_keeps_memberships(db, seed_deactivation_data, monkeypatch):
    """If a user is reactivated (deactivation row removed), their memberships survive."""
    from scripts.cleanup_deactivated_memberships import cleanup_expired_memberships

    db.query(S3UserDeactivation).filter(
        S3UserDeactivation.user_id == seed_deactivation_data["expired_user_id"]
    ).delete()
    db.flush()

    monkeypatch.setattr("scripts.cleanup_deactivated_memberships.Session", lambda: db)

    result = cleanup_expired_memberships(grace_days=30, dry_run=False)

    remaining = db.query(GroupMembership).filter(
        GroupMembership.user_id == seed_deactivation_data["expired_user_id"]
    ).count()
    assert remaining == 1, "Reactivated user memberships should survive"


def test_grace_days_validation():
    """--grace-days < 1 should be rejected."""
    import subprocess
    import os

    script_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "cleanup_deactivated_memberships.py")
    result = subprocess.run(
        ["python", script_path, "--grace-days", "0"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "at least 1" in result.stderr or "grace-days" in result.stderr.lower()
