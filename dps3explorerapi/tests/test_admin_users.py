"""
Tests for GET /admin/users, /admin/users/stats, /admin/users/export.

Covers:
  - Role-scope isolation (global admin vs org admin)
  - org_id validation (invalid → 400)
  - Pagination bounds and stable ordering
  - Search (case-insensitive partial match)
  - Response-contract key checks
  - Payload truncation (groups_total / folder_access_total)
"""

import pytest

from conftest import (
    MASTER_ADMIN,
    ORG_ADMIN,
    SUPER_ADMIN,
    USER_OTHER_ORG,
    USER_RW,
    USER_RW_2,
)
from core.auth import UAMUser, ROLE_ADMIN, ROLE_MASTER_ADMIN, ROLE_USER
from db.models import FolderGrant, GroupMembership, Org, S3UserDeactivation, UserGroup

API = "/api/v2/explorer/admin"

REQUIRED_ROW_KEYS = {
    "id", "user_name", "email", "role_id", "role_label",
    "subscription_id", "org_name", "active", "uam_active", "s3_deactivated",
    "groups", "groups_total",
    "folder_access", "folder_access_total",
}

REQUIRED_LIST_KEYS = {"results", "total", "page", "page_size"}
REQUIRED_STATS_KEYS = {"total_users", "master_admins", "active", "groups"}


def _seed_full(db):
    """Seed orgs, users, groups, grants for a realistic test scenario."""
    org1 = Org(
        subscription_id="sub-001", org_name="Org1",
        bucket_name="bucket-1", region="us-east-1", onboarded_by=1,
    )
    org2 = Org(
        subscription_id="sub-999", org_name="Org2",
        bucket_name="bucket-2", region="us-east-1", onboarded_by=1,
    )
    db.add_all([org1, org2])
    db.flush()

    users = [
        UAMUser(id=MASTER_ADMIN.id, user_name="MasterAdmin", email="master@test.com",
                role=ROLE_MASTER_ADMIN, subscription_id="sub-001", active=True),
        UAMUser(id=ORG_ADMIN.id, user_name="OrgAdmin", email="orgadmin@test.com",
                role=ROLE_ADMIN, subscription_id="sub-001", active=True),
        UAMUser(id=USER_RW.id, user_name="Alice", email="alice@test.com",
                role=ROLE_USER, subscription_id="sub-001", active=True),
        UAMUser(id=USER_RW_2.id, user_name="Bob", email="bob@test.com",
                role=ROLE_USER, subscription_id="sub-001", active=False),
        UAMUser(id=USER_OTHER_ORG.id, user_name="Charlie", email="charlie@other.com",
                role=ROLE_USER, subscription_id="sub-999", active=True),
    ]
    for u in users:
        db.merge(u)
    db.flush()

    grp = UserGroup(name="TeamAlpha", org_id=org1.id, created_by=ORG_ADMIN.id)
    db.add(grp)
    db.flush()

    db.add(GroupMembership(group_id=grp.id, user_id=USER_RW.id, added_by=ORG_ADMIN.id))
    db.flush()

    db.add(FolderGrant(
        group_id=grp.id, org_id=org1.id, prefix="Reports/", access_level="read_write",
        created_by=ORG_ADMIN.id,
    ))
    db.commit()
    return org1, org2, grp


# ── Response-contract tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_response_keys(client_as, db):
    """Every row must contain the full set of expected keys."""
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users")
    assert r.status_code == 200
    body = r.json()
    assert REQUIRED_LIST_KEYS <= body.keys()
    for row in body["results"]:
        assert REQUIRED_ROW_KEYS <= row.keys(), f"Missing keys: {REQUIRED_ROW_KEYS - row.keys()}"


@pytest.mark.asyncio
async def test_stats_response_keys(client_as, db):
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users/stats")
    assert r.status_code == 200
    assert REQUIRED_STATS_KEYS <= r.json().keys()


# ── Role-scope isolation ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_global_admin_sees_all_users(client_as, db):
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users")
    assert r.status_code == 200
    body = r.json()
    ids = {u["id"] for u in body["results"]}
    assert USER_OTHER_ORG.id in ids, "Global admin should see users from all orgs"
    assert body["total"] == 5


@pytest.mark.asyncio
async def test_org_admin_sees_only_own_org(client_as, db):
    _seed_full(db)
    async with client_as(ORG_ADMIN) as c:
        r = await c.get(f"{API}/users")
    body = r.json()
    ids = {u["id"] for u in body["results"]}
    assert USER_OTHER_ORG.id not in ids, "Org admin must not see other-org users"


@pytest.mark.asyncio
async def test_org_admin_ignores_foreign_org_id(client_as, db):
    """Org admin passing another org's org_id should still only see own org."""
    org1, org2, _ = _seed_full(db)
    async with client_as(ORG_ADMIN) as c:
        r = await c.get(f"{API}/users", params={"org_id": org2.id})
    body = r.json()
    ids = {u["id"] for u in body["results"]}
    assert USER_OTHER_ORG.id not in ids


@pytest.mark.asyncio
async def test_normal_user_blocked(client_as, db):
    _seed_full(db)
    async with client_as(USER_RW) as c:
        r = await c.get(f"{API}/users")
    assert r.status_code in (401, 403)


# ── org_id validation ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_org_id_returns_400(client_as, db):
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users", params={"org_id": 99999})
    assert r.status_code == 400
    assert "99999" in r.json()["detail"]


@pytest.mark.asyncio
async def test_valid_org_id_filters(client_as, db):
    org1, org2, _ = _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users", params={"org_id": org2.id})
    body = r.json()
    ids = {u["id"] for u in body["results"]}
    assert USER_OTHER_ORG.id in ids
    assert USER_RW.id not in ids


# ── Pagination & ordering ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pagination_bounds(client_as, db):
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users", params={"page": 1, "page_size": 2})
    body = r.json()
    assert len(body["results"]) == 2
    assert body["total"] == 5
    assert body["page"] == 1


@pytest.mark.asyncio
async def test_page_size_max_enforced(client_as, db):
    """page_size > 100 should be rejected by FastAPI validation."""
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users", params={"page_size": 200})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_stable_ordering(client_as, db):
    """Two identical requests must return the same row order."""
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r1 = await c.get(f"{API}/users")
        r2 = await c.get(f"{API}/users")
    ids1 = [u["id"] for u in r1.json()["results"]]
    ids2 = [u["id"] for u in r2.json()["results"]]
    assert ids1 == ids2


# ── Search ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_by_name(client_as, db):
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users", params={"q": "alice"})
    body = r.json()
    assert body["total"] == 1
    assert body["results"][0]["user_name"] == "Alice"


@pytest.mark.asyncio
async def test_search_by_email(client_as, db):
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users", params={"q": "other.com"})
    body = r.json()
    assert body["total"] == 1
    assert body["results"][0]["id"] == USER_OTHER_ORG.id


@pytest.mark.asyncio
async def test_search_case_insensitive(client_as, db):
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users", params={"q": "ALICE"})
    assert r.json()["total"] == 1


# ── Payload truncation ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_groups_total_reflects_real_count(client_as, db):
    """groups_total must equal real membership count, even when groups is capped."""
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users", params={"q": "Alice"})
    row = r.json()["results"][0]
    assert row["groups_total"] >= len(row["groups"])
    assert row["groups_total"] == 1


# ── Stats ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stats_counts(client_as, db):
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users/stats")
    s = r.json()
    assert s["total_users"] == 5
    assert s["active"] == 4
    assert s["master_admins"] == 1
    assert s["groups"] >= 1


@pytest.mark.asyncio
async def test_stats_respects_org_filter(client_as, db):
    org1, org2, _ = _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users/stats", params={"org_id": org2.id})
    s = r.json()
    assert s["total_users"] == 1


# ── CSV export ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_csv_headers(client_as, db):
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users/export")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "users_export.csv" in r.headers["content-disposition"]
    lines = r.text.strip().replace("\r", "").split("\n")
    assert lines[0] == "Name,Email,Organization,Role,Groups,Folder Access,Status"
    assert len(lines) == 6  # header + 5 users


# ── Detail endpoint ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detail_returns_full_user(client_as, db):
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users/{USER_RW.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == USER_RW.id
    assert body["user_name"] == "Alice"
    assert "groups" in body
    assert "folder_access" in body
    assert "groups_total" not in body  # detail returns full arrays, no truncation


@pytest.mark.asyncio
async def test_detail_not_found(client_as, db):
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.get(f"{API}/users/99999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_detail_org_admin_blocked_cross_org(client_as, db):
    _seed_full(db)
    async with client_as(ORG_ADMIN) as c:
        r = await c.get(f"{API}/users/{USER_OTHER_ORG.id}")
    assert r.status_code == 403


# ── Deactivate ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deactivate_user(client_as, db):
    _seed_full(db)
    async with client_as(ORG_ADMIN) as c:
        r = await c.post(f"{API}/users/{USER_RW.id}/deactivate")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == USER_RW.id
    assert body["active"] is False
    assert body["uam_active"] is True
    assert body["s3_deactivated"] is True

    db.expire_all()
    target = db.query(UAMUser).filter(UAMUser.id == USER_RW.id).first()
    assert target.active is True
    assert (
        db.query(S3UserDeactivation)
        .filter(S3UserDeactivation.user_id == USER_RW.id)
        .first()
        is not None
    )


@pytest.mark.asyncio
async def test_deactivate_uam_inactive_blocked(client_as, db):
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.post(f"{API}/users/{USER_RW_2.id}/deactivate")
    assert r.status_code == 400
    assert "uam" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_deactivate_already_s3_inactive(client_as, db):
    _seed_full(db)
    db.add(S3UserDeactivation(user_id=USER_RW.id, deactivated_by=ORG_ADMIN.id))
    db.commit()
    async with client_as(ORG_ADMIN) as c:
        r = await c.post(f"{API}/users/{USER_RW.id}/deactivate")
    assert r.status_code == 400
    assert "s3 explorer" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_deactivate_self_blocked(client_as, db):
    _seed_full(db)
    async with client_as(ORG_ADMIN) as c:
        r = await c.post(f"{API}/users/{ORG_ADMIN.id}/deactivate")
    assert r.status_code == 400
    assert "own account" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_deactivate_cross_org_blocked(client_as, db):
    _seed_full(db)
    async with client_as(ORG_ADMIN) as c:
        r = await c.post(f"{API}/users/{USER_OTHER_ORG.id}/deactivate")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_deactivate_global_admin_blocked_for_org_admin(client_as, db):
    _seed_full(db)
    async with client_as(ORG_ADMIN) as c:
        r = await c.post(f"{API}/users/{MASTER_ADMIN.id}/deactivate")
    assert r.status_code == 403


# ── Reactivate ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reactivate_after_s3_deactivate(client_as, db):
    _seed_full(db)
    async with client_as(ORG_ADMIN) as c:
        r = await c.post(f"{API}/users/{USER_RW.id}/deactivate")
    assert r.status_code == 200

    async with client_as(MASTER_ADMIN) as c:
        r = await c.post(f"{API}/users/{USER_RW.id}/reactivate")
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is True
    assert body["s3_deactivated"] is False
    assert (
        db.query(S3UserDeactivation)
        .filter(S3UserDeactivation.user_id == USER_RW.id)
        .first()
        is None
    )


@pytest.mark.asyncio
async def test_reactivate_uam_inactive_blocked(client_as, db):
    _seed_full(db)
    db.add(S3UserDeactivation(user_id=USER_RW_2.id, deactivated_by=MASTER_ADMIN.id))
    db.commit()
    async with client_as(MASTER_ADMIN) as c:
        r = await c.post(f"{API}/users/{USER_RW_2.id}/reactivate")
    assert r.status_code == 400
    assert "uam" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reactivate_org_admin_blocked(client_as, db):
    _seed_full(db)
    db.add(S3UserDeactivation(user_id=USER_RW.id, deactivated_by=ORG_ADMIN.id))
    db.commit()
    async with client_as(ORG_ADMIN) as c:
        r = await c.post(f"{API}/users/{USER_RW.id}/reactivate")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_reactivate_not_s3_deactivated(client_as, db):
    _seed_full(db)
    async with client_as(MASTER_ADMIN) as c:
        r = await c.post(f"{API}/users/{USER_RW.id}/reactivate")
    assert r.status_code == 400
    assert "s3 explorer" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reactivate_after_grace_expired(client_as, db):
    from datetime import datetime, timedelta, timezone

    from api.endpoints.users import DEACTIVATION_GRACE_DAYS

    _seed_full(db)
    expired_at = datetime.now(timezone.utc) - timedelta(days=DEACTIVATION_GRACE_DAYS + 1)
    db.add(
        S3UserDeactivation(
            user_id=USER_RW.id,
            deactivated_by=ORG_ADMIN.id,
            deactivated_at=expired_at,
        )
    )
    db.commit()

    async with client_as(MASTER_ADMIN) as c:
        r = await c.post(f"{API}/users/{USER_RW.id}/reactivate")
    assert r.status_code == 400
    assert "expired" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_auth_blocks_s3_deactivated(db):
    from unittest.mock import MagicMock

    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    from jose import jwt

    from core.auth import get_current_user
    from core.config import settings

    _seed_full(db)
    db.add(S3UserDeactivation(user_id=USER_RW.id, deactivated_by=ORG_ADMIN.id))
    db.commit()

    token = jwt.encode(
        {
            "user_id": USER_RW.id,
            "email": USER_RW.email,
            "type": "access",
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    request = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, credentials, db)

    assert exc_info.value.status_code == 403
    assert "s3 explorer" in exc_info.value.detail.lower()
