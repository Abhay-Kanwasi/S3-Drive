"""Tests for OTP send/verify and group-delete approver flow."""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import ORG_ADMIN, SUPER_ADMIN
from db.models import Org, UserGroup, FolderGrant, AdminOtpChallenge
from core.auth import ROLE_MASTER_ADMIN, ROLE_SUPER_ADMIN, UAMUser
from core.otp import create_and_send_otp

ADMIN_API = "/api/v2/explorer/admin"
GROUPS_API = "/api/v2/explorer/admin/groups"


@pytest.fixture
def seed_org(db):
    org = Org(
        subscription_id="sub-001",
        org_name="OtpOrg",
        bucket_name="otp-bucket",
        region="us-east-1",
        onboarded_by=SUPER_ADMIN.id,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def seed_approver_users(db):
    """Onboarder (super) + org admin; unrelated master admin must not appear in approvers."""
    db.merge(
        UAMUser(
            id=SUPER_ADMIN.id,
            user_name=SUPER_ADMIN.user_name,
            email=SUPER_ADMIN.email,
            role=ROLE_SUPER_ADMIN,
            subscription_id="sub-001",
            active=True,
        )
    )
    db.merge(
        UAMUser(
            id=ORG_ADMIN.id,
            user_name=ORG_ADMIN.user_name,
            email=ORG_ADMIN.email,
            role=1,
            subscription_id="sub-001",
            active=True,
        )
    )
    db.merge(
        UAMUser(
            id=99,
            user_name="Other Master",
            email="other-master@test.com",
            role=ROLE_MASTER_ADMIN,
            subscription_id="sub-999",
            active=True,
        )
    )
    db.commit()


@pytest.fixture
def seed_group_with_grant(db, seed_org):
    g = UserGroup(org_id=seed_org.id, name="dp-OtpTest", created_by=ORG_ADMIN.id)
    db.add(g)
    db.flush()
    db.add(
        FolderGrant(
            group_id=g.id,
            org_id=seed_org.id,
            prefix="data/",
            access_level="read",
            created_by=ORG_ADMIN.id,
        )
    )
    db.commit()
    db.refresh(g)
    return g


@pytest.mark.asyncio
async def test_send_otp_requires_smtp_config(client_as):
    with patch("api.endpoints.otp.smtp_configured", return_value=False):
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{ADMIN_API}/otp/send", json={})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_send_and_verify_otp(client_as, db):
    with (
        patch("api.endpoints.otp.smtp_configured", return_value=True),
        patch("core.otp.smtp_configured", return_value=True),
        patch("core.otp.send_smtp_html"),
    ):
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(f"{ADMIN_API}/otp/send", json={"purpose": "sensitive_action"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["sent"] is True
        assert data["expires_in_seconds"] == 600

    row = (
        db.query(AdminOtpChallenge)
        .filter(AdminOtpChallenge.user_id == SUPER_ADMIN.id)
        .order_by(AdminOtpChallenge.id.desc())
        .first()
    )
    assert row is not None

    async with client_as(SUPER_ADMIN) as c:
        bad = await c.post(
            f"{ADMIN_API}/otp/verify",
            json={"code": "000000", "purpose": "sensitive_action"},
        )
    assert bad.json()["valid"] is False


@pytest.mark.asyncio
async def test_list_otp_approvers_onboarder_and_org_admins_only(
    client_as, seed_org, seed_approver_users
):
    async with client_as(ORG_ADMIN) as c:
        resp = await c.get(f"{ADMIN_API}/otp/approvers", params={"org_id": seed_org.id})
    assert resp.status_code == 200
    data = resp.json()
    ids = {r["id"] for r in data}
    assert SUPER_ADMIN.id in ids
    assert ORG_ADMIN.id in ids
    assert 99 not in ids
    onboarder_rows = [r for r in data if r["is_onboarder"]]
    assert len(onboarder_rows) == 1
    assert onboarder_rows[0]["id"] == SUPER_ADMIN.id
    assert all(r["role_label"] in ("admin", "super_admin") for r in data)


@pytest.mark.asyncio
async def test_delete_group_with_grants_requires_email_approval(
    client_as, seed_group_with_grant, seed_approver_users
):
    gid = seed_group_with_grant.id
    async with client_as(ORG_ADMIN) as c:
        resp = await c.request("DELETE", f"{GROUPS_API}/{gid}", json={})
    assert resp.status_code == 400
    assert "Email approval required" in resp.json()["detail"]
