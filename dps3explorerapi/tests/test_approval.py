"""Tests for email approve/reject group delete flow."""

import os
import re
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import ORG_ADMIN, SUPER_ADMIN
from db.models import Org, UserGroup, FolderGrant, AdminApprovalRequest
from core.auth import ROLE_SUPER_ADMIN, UAMUser

ADMIN_API = "/api/v2/explorer/admin"
GROUPS_API = "/api/v2/explorer/admin/groups"


def _parse_action_link(html: str, action: str):
    from urllib.parse import parse_qs, urlparse

    normalized = html.replace("&amp;", "&")
    for m in re.finditer(r'href="([^"]+)"', normalized):
        url = m.group(1)
        if f"action={action}" not in url:
            continue
        qs = parse_qs(urlparse(url).query)
        return int(qs["id"][0]), qs["token"][0]
    return None, None


@pytest.fixture
def seed_org(db):
    org = Org(
        subscription_id="sub-001",
        org_name="ApprovalOrg",
        bucket_name="approval-bucket",
        region="us-east-1",
        onboarded_by=SUPER_ADMIN.id,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def seed_approver_users(db):
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
    db.commit()


@pytest.fixture
def seed_group_with_grant(db, seed_org):
    g = UserGroup(
        org_id=seed_org.id,
        name="dp-ApprovalTest",
        created_by=ORG_ADMIN.id,
        requires_delete_approval=True,
    )
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
async def test_delete_group_with_grants_requires_email_approval(
    client_as, seed_group_with_grant, seed_approver_users
):
    gid = seed_group_with_grant.id
    async with client_as(ORG_ADMIN) as c:
        resp = await c.request("DELETE", f"{GROUPS_API}/{gid}", json={})
    assert resp.status_code == 400
    assert "Email approval required" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_send_group_delete_approval_email(
    client_as, seed_group_with_grant, seed_approver_users
):
    gid = seed_group_with_grant.id
    captured = {}

    with (
        patch("api.endpoints.otp.smtp_configured", return_value=True),
        patch("core.approval.smtp_configured", return_value=True),
        patch(
            "core.approval.send_smtp_html",
            side_effect=lambda **kw: captured.update({"html": kw.get("html_body", "")}),
        ),
    ):
        async with client_as(ORG_ADMIN) as c:
            resp = await c.post(
                f"{ADMIN_API}/otp/send",
                json={
                    "purpose": f"group_delete:{gid}",
                    "recipient_user_id": SUPER_ADMIN.id,
                },
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["approval_required"] is True
    assert "Review and approve" in captured.get("html", "")
    assert "Review and reject" in captured.get("html", "")


@pytest.mark.asyncio
async def test_approve_link_deletes_group(
    client_as, db, seed_group_with_grant, seed_approver_users
):
    from core.approval import create_and_send_group_delete_approval

    gid = seed_group_with_grant.id
    approver = db.query(UAMUser).filter(UAMUser.id == SUPER_ADMIN.id).first()
    captured = {}

    with patch("core.approval.smtp_configured", return_value=True), patch(
        "core.approval.send_smtp_html",
        side_effect=lambda **kw: captured.update({"html": kw.get("html_body", "")}),
    ):
        create_and_send_group_delete_approval(
            db,
            group_id=gid,
            approver=approver,
            requester=ORG_ADMIN,
            request_base_url="http://testserver/api/v2/explorer",
        )
        db.commit()

    html = captured.get("html", "")
    approval_id, token = _parse_action_link(html, "approve")
    assert token, f"Approve link not found in: {html[:800]}"

    async with client_as(ORG_ADMIN) as c:
        preview = await c.get(
            f"{ADMIN_API}/approval/respond",
            params={"id": approval_id, "token": token, "action": "approve"},
        )
    assert preview.status_code == 200
    assert "Confirm deletion" in preview.text
    assert "Group deleted" not in preview.text

    async with client_as(ORG_ADMIN) as c:
        get_resp = await c.get(f"{GROUPS_API}/{gid}")
    assert get_resp.status_code == 200

    async with client_as(SUPER_ADMIN) as c:
        resp = await c.post(
            f"{ADMIN_API}/approval/respond",
            data={"id": approval_id, "token": token, "action": "approve"},
        )
    assert resp.status_code == 200
    assert "Group deleted" in resp.text

    async with client_as(ORG_ADMIN) as c:
        get_resp = await c.get(f"{GROUPS_API}/{gid}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_reject_link_keeps_group(
    client_as, db, seed_group_with_grant, seed_approver_users
):
    from core.approval import create_and_send_group_delete_approval

    gid = seed_group_with_grant.id
    approver = db.query(UAMUser).filter(UAMUser.id == SUPER_ADMIN.id).first()
    captured = {}

    with patch("core.approval.smtp_configured", return_value=True), patch(
        "core.approval.send_smtp_html",
        side_effect=lambda **kw: captured.update({"html": kw.get("html_body", "")}),
    ):
        create_and_send_group_delete_approval(
            db,
            group_id=gid,
            approver=approver,
            requester=ORG_ADMIN,
            request_base_url="http://testserver/api/v2/explorer",
        )
        db.commit()

    html = captured.get("html", "")
    approval_id, token = _parse_action_link(html, "reject")
    assert token

    async with client_as(SUPER_ADMIN) as c:
        resp = await c.post(
            f"{ADMIN_API}/approval/respond",
            data={"id": approval_id, "token": token, "action": "reject"},
        )
    assert resp.status_code == 200
    assert "rejected" in resp.text.lower()

    row = db.query(AdminApprovalRequest).filter(AdminApprovalRequest.id == approval_id).first()
    assert row.status == "rejected"

    async with client_as(ORG_ADMIN) as c:
        get_resp = await c.get(f"{GROUPS_API}/{gid}")
    assert get_resp.status_code == 200


@pytest.mark.asyncio
async def test_get_approve_prefetch_does_not_delete(
    client_as, db, seed_group_with_grant, seed_approver_users
):
    from core.approval import create_and_send_group_delete_approval

    gid = seed_group_with_grant.id
    approver = db.query(UAMUser).filter(UAMUser.id == SUPER_ADMIN.id).first()
    captured = {}

    with patch("core.approval.smtp_configured", return_value=True), patch(
        "core.approval.send_smtp_html",
        side_effect=lambda **kw: captured.update({"html": kw.get("html_body", "")}),
    ):
        create_and_send_group_delete_approval(
            db,
            group_id=gid,
            approver=approver,
            requester=ORG_ADMIN,
            request_base_url="http://testserver/api/v2/explorer",
        )
        db.commit()

    approval_id, token = _parse_action_link(captured["html"], "approve")
    async with client_as(ORG_ADMIN) as c:
        await c.get(
            f"{ADMIN_API}/approval/respond",
            params={"id": approval_id, "token": token, "action": "approve"},
        )
        get_resp = await c.get(f"{GROUPS_API}/{gid}")
    assert get_resp.status_code == 200


@pytest.mark.asyncio
async def test_cannot_strip_grants_then_delete_without_approval(
    client_as, seed_group_with_grant, seed_approver_users, db
):
    gid = seed_group_with_grant.id
    grant = db.query(FolderGrant).filter(FolderGrant.group_id == gid).first()
    async with client_as(ORG_ADMIN) as c:
        await c.delete(f"{GROUPS_API}/{gid}/grants/{grant.id}")
        resp = await c.delete(f"{GROUPS_API}/{gid}")
    assert resp.status_code == 400
    assert "Email approval required" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_approve_via_json_body_deletes_group(
    client_as, db, seed_group_with_grant, seed_approver_users
):
    """SPA path: POST JSON body returns JSON and performs the delete."""
    from core.approval import create_and_send_group_delete_approval

    gid = seed_group_with_grant.id
    approver = db.query(UAMUser).filter(UAMUser.id == SUPER_ADMIN.id).first()
    captured = {}

    with patch("core.approval.smtp_configured", return_value=True), patch(
        "core.approval.send_smtp_html",
        side_effect=lambda **kw: captured.update({"html": kw.get("html_body", "")}),
    ):
        create_and_send_group_delete_approval(
            db,
            group_id=gid,
            approver=approver,
            requester=ORG_ADMIN,
            request_base_url="http://testserver/api/v2/explorer",
        )
        db.commit()

    approval_id, token = _parse_action_link(captured["html"], "approve")

    async with client_as(SUPER_ADMIN) as c:
        resp = await c.post(
            f"{ADMIN_API}/approval/respond",
            json={"id": approval_id, "token": token, "action": "approve"},
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    payload = resp.json()
    assert payload["kind"] == "group_delete"
    assert payload["action"] == "approve"
    assert payload["group_name"] == "dp-ApprovalTest"

    async with client_as(ORG_ADMIN) as c:
        get_resp = await c.get(f"{GROUPS_API}/{gid}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_via_json_html_in_name_is_escaped(
    client_as, db, seed_org, seed_approver_users
):
    """A group name with HTML must come back escaped in message_html."""
    from core.approval import create_and_send_group_delete_approval

    g = UserGroup(
        org_id=seed_org.id,
        name="dp-<script>alert(1)</script>",
        created_by=ORG_ADMIN.id,
        requires_delete_approval=True,
    )
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

    approver = db.query(UAMUser).filter(UAMUser.id == SUPER_ADMIN.id).first()
    captured = {}
    with patch("core.approval.smtp_configured", return_value=True), patch(
        "core.approval.send_smtp_html",
        side_effect=lambda **kw: captured.update({"html": kw.get("html_body", "")}),
    ):
        create_and_send_group_delete_approval(
            db,
            group_id=g.id,
            approver=approver,
            requester=ORG_ADMIN,
            request_base_url="http://testserver/api/v2/explorer",
        )
        db.commit()

    approval_id, token = _parse_action_link(captured["html"], "approve")

    async with client_as(SUPER_ADMIN) as c:
        resp = await c.post(
            f"{ADMIN_API}/approval/respond",
            json={"id": approval_id, "token": token, "action": "approve"},
        )
    payload = resp.json()
    assert "<script>" not in payload["message_html"]
    assert "&lt;script&gt;" in payload["message_html"]
    assert payload["group_name"] == "dp-<script>alert(1)</script>"


@pytest.mark.asyncio
async def test_post_respond_requires_auth(
    db, seed_group_with_grant, seed_approver_users, mock_s3, setup_db
):
    """POST /admin/approval/respond must reject unauthenticated requests (no Bearer token)."""
    import httpx
    from httpx import ASGITransport
    from main import app
    from api.router import api_router
    from core.config import settings as app_settings
    from core.approval import create_and_send_group_delete_approval

    if not any(
        getattr(r, "path", "") == f"{app_settings.API_V1_STR}/browse/browse"
        for r in app.routes
    ):
        app.include_router(api_router, prefix=app_settings.API_V1_STR)

    gid = seed_group_with_grant.id
    approver = db.query(UAMUser).filter(UAMUser.id == SUPER_ADMIN.id).first()
    captured = {}
    with patch("core.approval.smtp_configured", return_value=True), patch(
        "core.approval.send_smtp_html",
        side_effect=lambda **kw: captured.update({"html": kw.get("html_body", "")}),
    ):
        create_and_send_group_delete_approval(
            db,
            group_id=gid,
            approver=approver,
            requester=ORG_ADMIN,
            request_base_url="http://testserver/api/v2/explorer",
        )
        db.commit()

    approval_id, token = _parse_action_link(captured["html"], "approve")

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp_form = await c.post(
            f"{ADMIN_API}/approval/respond",
            data={"id": approval_id, "token": token, "action": "approve"},
        )
        resp_json = await c.post(
            f"{ADMIN_API}/approval/respond",
            json={"id": approval_id, "token": token, "action": "approve"},
        )
    assert resp_form.status_code in (401, 403)
    assert resp_json.status_code in (401, 403)


@pytest.mark.asyncio
async def test_cannot_self_approve_group_delete(
    client_as, seed_group_with_grant, seed_approver_users
):
    gid = seed_group_with_grant.id
    with (
        patch("api.endpoints.otp.smtp_configured", return_value=True),
        patch("core.approval.smtp_configured", return_value=True),
        patch("core.approval.send_smtp_html"),
    ):
        async with client_as(ORG_ADMIN) as c:
            resp = await c.post(
                f"{ADMIN_API}/otp/send",
                json={
                    "purpose": f"group_delete:{gid}",
                    "recipient_user_id": ORG_ADMIN.id,
                },
            )
    assert resp.status_code == 400
    assert "yourself" in resp.json()["detail"].lower()
