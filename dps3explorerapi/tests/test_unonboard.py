"""Tests for 4-eyes un-onboard (requester OTP + approver email)."""

import os
import re
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import SUPER_ADMIN, ORG_ADMIN
from tests.test_approval import _parse_action_link
from db.models import Org, FolderGrant, UserGroup, UnonboardRequest
from core.auth import ROLE_SUPER_ADMIN, ROLE_MASTER_ADMIN, UAMUser
from core.otp import create_and_send_otp
from core.unonboard import unonboard_submit_purpose

ADMIN = "/api/v2/explorer/admin"


@pytest.fixture
def seed_org(db):
    org = Org(
        subscription_id="sub-unonboard",
        org_name="UnonboardCo",
        bucket_name="unonboard-bucket",
        region="us-east-1",
        onboarded_by=SUPER_ADMIN.id,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def seed_master_admins(db):
    db.merge(
        UAMUser(
            id=SUPER_ADMIN.id,
            user_name=SUPER_ADMIN.user_name,
            email=SUPER_ADMIN.email,
            role=ROLE_SUPER_ADMIN,
            subscription_id="sub-unonboard",
            active=True,
        )
    )
    db.merge(
        UAMUser(
            id=ORG_ADMIN.id,
            user_name=ORG_ADMIN.user_name,
            email=ORG_ADMIN.email,
            role=ROLE_MASTER_ADMIN,
            subscription_id="sub-other",
            active=True,
        )
    )
    db.commit()


@pytest.fixture
def seed_org_with_grant(db, seed_org):
    g = UserGroup(org_id=seed_org.id, name="dp-Keep", created_by=SUPER_ADMIN.id)
    db.add(g)
    db.flush()
    db.add(
        FolderGrant(
            group_id=g.id,
            org_id=seed_org.id,
            prefix="data/",
            access_level="read",
            created_by=SUPER_ADMIN.id,
        )
    )
    db.commit()
    return seed_org


@pytest.mark.asyncio
async def test_list_unonboard_approvers_excludes_self(client_as, seed_master_admins):
    async with client_as(SUPER_ADMIN) as c:
        resp = await c.get(f"{ADMIN}/unonboard/approvers")
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()}
    assert SUPER_ADMIN.id not in ids
    assert ORG_ADMIN.id in ids


@pytest.mark.asyncio
async def test_unonboard_request_and_email_approve(
    client_as, db, seed_org_with_grant, seed_master_admins
):
    org = seed_org_with_grant
    org_id = org.id
    purpose = unonboard_submit_purpose(org_id)
    captured = {}

    with patch("core.unonboard.smtp_configured", return_value=True), patch(
        "core.otp.smtp_configured", return_value=True
    ), patch("core.otp.send_smtp_html") as mock_otp, patch(
        "core.unonboard.send_smtp_html",
        side_effect=lambda **kw: captured.update({"html": kw.get("html_body", "")}),
    ):
        create_and_send_otp(
            db,
            user_id=SUPER_ADMIN.id,
            email=SUPER_ADMIN.email,
            user_name=SUPER_ADMIN.user_name,
            purpose=purpose,
        )
        db.commit()
        m = re.search(r">(\d{6})<", mock_otp.call_args.kwargs.get("html_body", ""))
        code = m.group(1)

        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(
                f"{ADMIN}/orgs/{org_id}/unonboard/request",
                json={"approver_user_id": ORG_ADMIN.id, "otp_code": code},
            )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending_approval"

    approval_id, token = _parse_action_link(captured["html"], "approve")
    assert token

    async with client_as(SUPER_ADMIN) as c:
        preview = await c.get(
            f"{ADMIN}/approval/respond",
            params={"id": approval_id, "token": token, "action": "approve"},
        )
    assert "Confirm un-onboard" in preview.text

    async with client_as(ORG_ADMIN) as c:
        confirm = await c.post(
            f"{ADMIN}/approval/respond",
            data={"id": approval_id, "token": token, "action": "approve"},
        )
    assert confirm.status_code == 200
    assert "un-onboarded" in confirm.text.lower()

    db.expire_all()
    assert db.query(Org).filter(Org.id == org_id).first() is None
    assert db.query(FolderGrant).filter(FolderGrant.org_id == org_id).count() == 0
    assert db.query(UserGroup).filter(UserGroup.org_id == org_id).count() == 0
    req_row = (
        db.query(UnonboardRequest)
        .filter(UnonboardRequest.org_name == "UnonboardCo", UnonboardRequest.status == "approved")
        .first()
    )
    assert req_row is not None
    assert req_row.org_id is None
    assert req_row.bucket_name == "unonboard-bucket"


@pytest.mark.asyncio
async def test_unonboard_email_reject_keeps_org_active(
    client_as, db, seed_org_with_grant, seed_master_admins
):
    org = seed_org_with_grant
    purpose = unonboard_submit_purpose(org.id)
    captured = {}

    with patch("core.unonboard.smtp_configured", return_value=True), patch(
        "core.otp.smtp_configured", return_value=True
    ), patch("core.otp.send_smtp_html") as mock_otp, patch(
        "core.unonboard.send_smtp_html",
        side_effect=lambda **kw: captured.update({"html": kw.get("html_body", "")}),
    ):
        create_and_send_otp(
            db,
            user_id=SUPER_ADMIN.id,
            email=SUPER_ADMIN.email,
            user_name=SUPER_ADMIN.user_name,
            purpose=purpose,
        )
        db.commit()
        code = re.search(r">(\d{6})<", mock_otp.call_args.kwargs.get("html_body", "")).group(1)

        async with client_as(SUPER_ADMIN) as c:
            await c.post(
                f"{ADMIN}/orgs/{org.id}/unonboard/request",
                json={"approver_user_id": ORG_ADMIN.id, "otp_code": code},
            )

    approval_id, token = _parse_action_link(captured["html"], "reject")
    async with client_as(ORG_ADMIN) as c:
        resp = await c.post(
            f"{ADMIN}/approval/respond",
            data={"id": approval_id, "token": token, "action": "reject"},
        )
    assert resp.status_code == 200

    db.expire_all()
    org_row = db.query(Org).filter(Org.id == org.id).first()
    assert org_row is not None
    assert org_row.is_active is True
    assert db.query(FolderGrant).filter(FolderGrant.org_id == org.id).count() == 1


@pytest.mark.asyncio
async def test_unonboard_wrong_approver_blocked(
    client_as, db, seed_org_with_grant, seed_master_admins
):
    org = seed_org_with_grant
    purpose = unonboard_submit_purpose(org.id)
    captured = {}

    with patch("core.unonboard.smtp_configured", return_value=True), patch(
        "core.otp.smtp_configured", return_value=True
    ), patch("core.otp.send_smtp_html") as mock_otp, patch(
        "core.unonboard.send_smtp_html",
        side_effect=lambda **kw: captured.update({"html": kw.get("html_body", "")}),
    ):
        create_and_send_otp(
            db,
            user_id=SUPER_ADMIN.id,
            email=SUPER_ADMIN.email,
            user_name=SUPER_ADMIN.user_name,
            purpose=purpose,
        )
        db.commit()
        code = re.search(r">(\d{6})<", mock_otp.call_args.kwargs.get("html_body", "")).group(1)
        async with client_as(SUPER_ADMIN) as c:
            await c.post(
                f"{ADMIN}/orgs/{org.id}/unonboard/request",
                json={"approver_user_id": ORG_ADMIN.id, "otp_code": code},
            )

    approval_id, token = _parse_action_link(captured["html"], "approve")
    async with client_as(SUPER_ADMIN) as c:
        resp = await c.post(
            f"{ADMIN}/approval/respond",
            data={"id": approval_id, "token": token, "action": "approve"},
        )
    assert resp.status_code == 403
    assert "approver" in resp.text.lower()

    db.expire_all()
    assert db.query(Org).filter(Org.id == org.id).first() is not None


@pytest.mark.asyncio
async def test_unonboard_self_approver_rejected(client_as, db, seed_org, seed_master_admins):
    org = seed_org
    purpose = unonboard_submit_purpose(org.id)
    with patch("core.unonboard.smtp_configured", return_value=True), patch(
        "core.otp.smtp_configured", return_value=True
    ), patch("core.otp.send_smtp_html") as mock_otp, patch(
        "core.unonboard.send_smtp_html"
    ):
        create_and_send_otp(
            db,
            user_id=SUPER_ADMIN.id,
            email=SUPER_ADMIN.email,
            user_name=SUPER_ADMIN.user_name,
            purpose=purpose,
        )
        db.commit()
        code = re.search(r">(\d{6})<", mock_otp.call_args.kwargs.get("html_body", "")).group(1)
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post(
                f"{ADMIN}/orgs/{org.id}/unonboard/request",
                json={"approver_user_id": SUPER_ADMIN.id, "otp_code": code},
            )
    assert resp.status_code == 400
    assert "your own" in resp.json()["detail"].lower()
