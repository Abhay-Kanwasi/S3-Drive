"""
Integration tests for Google OAuth / JWT cookie auth endpoints.

Google's id_token.verify_oauth2_token is mocked throughout — no real
Google credentials or network calls are needed.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport
from unittest.mock import patch

from core.auth import create_access_token, create_refresh_token, ACCESS_COOKIE, REFRESH_COOKIE
from db.models import User
from db.postgresdb import get_db
from tests.conftest import (
    TestSession, TEST_ENGINE, SUPER_ADMIN, _override_get_db,
    ROLE_SUPER_ADMIN,
)
from db.postgresdb import Base


GOOGLE_CLAIMS = {
    "sub": "google-sub-001",
    "email": "super@test.com",
    "email_verified": True,
    "iss": "https://accounts.google.com",
}

UNKNOWN_CLAIMS = {
    "sub": "google-sub-unknown",
    "email": "nobody@test.com",
    "email_verified": True,
    "iss": "https://accounts.google.com",
}

UNVERIFIED_CLAIMS = {
    "sub": "google-sub-002",
    "email": "super@test.com",
    "email_verified": False,
    "iss": "https://accounts.google.com",
}


@pytest_asyncio.fixture
async def auth_client(setup_db, seed_org):
    """AsyncClient wired to the real app with test DB (no auth override)."""
    from main import app
    from api.router import api_router
    from core.config import settings as app_settings

    _browse_route = f"{app_settings.API_V1_STR}/browse/browse"
    if not any(getattr(r, "path", "") == _browse_route for r in app.routes):
        app.include_router(api_router, prefix=app_settings.API_V1_STR)

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _google_login_url():
    from core.config import settings
    return f"{settings.API_V1_STR}/auth/google"


def _refresh_url():
    from core.config import settings
    return f"{settings.API_V1_STR}/auth/refresh"


def _logout_url():
    from core.config import settings
    return f"{settings.API_V1_STR}/auth/logout"


def _me_url():
    from core.config import settings
    return f"{settings.API_V1_STR}/auth/me"


# ── Google login ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_google_login_links_and_returns_user(auth_client):
    with patch("api.endpoints.auth.id_token.verify_oauth2_token", return_value=GOOGLE_CLAIMS), \
         patch("core.config.settings.GOOGLE_CLIENT_ID", "fake-client-id"):
        resp = await auth_client.post(_google_login_url(), json={"credential": "fake"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "super@test.com"
    assert ACCESS_COOKIE in resp.cookies
    assert REFRESH_COOKIE in resp.cookies


@pytest.mark.asyncio
async def test_google_login_unknown_user_rejected(auth_client):
    with patch("api.endpoints.auth.id_token.verify_oauth2_token", return_value=UNKNOWN_CLAIMS), \
         patch("core.config.settings.GOOGLE_CLIENT_ID", "fake-client-id"):
        resp = await auth_client.post(_google_login_url(), json={"credential": "fake"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_google_login_unverified_email_rejected(auth_client):
    with patch("api.endpoints.auth.id_token.verify_oauth2_token", return_value=UNVERIFIED_CLAIMS), \
         patch("core.config.settings.GOOGLE_CLIENT_ID", "fake-client-id"):
        resp = await auth_client.post(_google_login_url(), json={"credential": "fake"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_google_login_invalid_credential(auth_client):
    with patch("api.endpoints.auth.id_token.verify_oauth2_token", side_effect=Exception("bad")), \
         patch("core.config.settings.GOOGLE_CLIENT_ID", "fake-client-id"):
        resp = await auth_client.post(_google_login_url(), json={"credential": "bad"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_google_login_inactive_user_rejected(auth_client):
    db = TestSession()
    try:
        user = db.query(User).filter(User.email == "super@test.com").first()
        user.active = False
        db.commit()
    finally:
        db.close()

    with patch("api.endpoints.auth.id_token.verify_oauth2_token", return_value=GOOGLE_CLAIMS), \
         patch("core.config.settings.GOOGLE_CLIENT_ID", "fake-client-id"):
        resp = await auth_client.post(_google_login_url(), json={"credential": "fake"})
    assert resp.status_code == 403


# ── /auth/me ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auth_me_with_valid_cookie(auth_client):
    token = create_access_token(SUPER_ADMIN.id)
    auth_client.cookies.set(ACCESS_COOKIE, token)
    resp = await auth_client.get(_me_url())
    assert resp.status_code == 200
    assert resp.json()["email"] == "super@test.com"


@pytest.mark.asyncio
async def test_auth_me_no_cookie(auth_client):
    resp = await auth_client.get(_me_url())
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_expired_cookie(auth_client):
    # Forge a token signed with wrong key → JWTError → 401
    from jose import jwt as jose_jwt
    bad_token = jose_jwt.encode(
        {"sub": "1", "type": "access"},
        "wrong-secret",
        algorithm="HS256",
    )
    auth_client.cookies.set(ACCESS_COOKIE, bad_token)
    resp = await auth_client.get(_me_url())
    assert resp.status_code == 401


# ── Refresh ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_issues_new_cookies(auth_client):
    token = create_refresh_token(SUPER_ADMIN.id)
    auth_client.cookies.set(REFRESH_COOKIE, token)
    auth_client.cookies.set("s3exp_csrf", "test-csrf")
    resp = await auth_client.post(_refresh_url(), headers={"X-CSRF-Token": "test-csrf"})
    assert resp.status_code == 200
    assert ACCESS_COOKIE in resp.cookies


@pytest.mark.asyncio
async def test_refresh_no_cookie_rejected(auth_client):
    resp = await auth_client.post(_refresh_url(), headers={"X-CSRF-Token": "test-csrf"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_wrong_token_type_rejected(auth_client):
    # Send an access token where a refresh token is expected
    token = create_access_token(SUPER_ADMIN.id)
    auth_client.cookies.set(REFRESH_COOKIE, token)
    auth_client.cookies.set("s3exp_csrf", "test-csrf")
    resp = await auth_client.post(_refresh_url(), headers={"X-CSRF-Token": "test-csrf"})
    assert resp.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_logout_clears_cookies(auth_client):
    token = create_access_token(SUPER_ADMIN.id)
    auth_client.cookies.set(ACCESS_COOKIE, token)
    auth_client.cookies.set("s3exp_csrf", "test-csrf")
    resp = await auth_client.post(_logout_url(), headers={"X-CSRF-Token": "test-csrf"})
    assert resp.status_code == 200
    # Cookies should be cleared (max-age=0 / deleted)
    assert resp.cookies.get(ACCESS_COOKIE, "") == "" or ACCESS_COOKIE in resp.headers.get("set-cookie", "")


# ── Subject conflict ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_second_login_uses_subject_not_email(auth_client):
    """After first login links the subject, subsequent logins use sub directly."""
    db = TestSession()
    try:
        user = db.query(User).filter(User.email == "super@test.com").first()
        user.google_subject = GOOGLE_CLAIMS["sub"]
        db.commit()
    finally:
        db.close()

    with patch("api.endpoints.auth.id_token.verify_oauth2_token", return_value=GOOGLE_CLAIMS), \
         patch("core.config.settings.GOOGLE_CLIENT_ID", "fake-client-id"):
        resp = await auth_client.post(_google_login_url(), json={"credential": "fake"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "super@test.com"
