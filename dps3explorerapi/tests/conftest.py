"""
Shared fixtures for S3 Explorer test suite.

Uses:
- SQLite in-memory DB (no real Postgres needed)
- moto-mocked S3 (no real AWS needed)
- FastAPI dependency overrides for auth (no real JWT/UAM needed)

Run:
    cd dps3explorerapi
    pip install pytest pytest-asyncio httpx moto[s3]
    pytest tests/ -v
"""

from __future__ import annotations

import os
import sys

# Ensure the API package root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------- Patch env vars BEFORE any app code imports ----------
os.environ.setdefault("POSTGRES_DATABASE_URI", "sqlite:///")
os.environ.setdefault("BUCKET", "test-bucket")
os.environ.setdefault("env", "test")
os.environ.setdefault("clientId", "test")
os.environ.setdefault("clientSecret", "test")
os.environ.setdefault("tenantId", "test")
os.environ.setdefault("userId", "1")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("DB_SCHEMA", "main")
os.environ.setdefault("TRASH_BUCKET", "test-trash-bucket")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

import boto3
import pytest
import pytest_asyncio
from moto import mock_aws
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.auth import (
    CurrentUser,
    ROLE_ADMIN,
    ROLE_USER,
    ROLE_MASTER_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_LABELS,
    ADMIN_ROLE_IDS,
    get_current_user,
)
from db.postgresdb import Base, get_db
from db.models import Org, FolderMetadata, Explorer

# ---------- SQLite in-memory engine ----------

TEST_ENGINE = create_engine(
    "sqlite://",
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(TEST_ENGINE, "connect")
def _set_sqlite_pragma(dbapi_conn, _rec):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    # Attach the same in-memory DB under the "rhymedatapoem" alias
    # so that schema-qualified table names resolve.
    cursor.execute("ATTACH DATABASE ':memory:' AS rhymedatapoem")
    cursor.close()


TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


# ---------- Pre-built user identities ----------

SUPER_ADMIN = CurrentUser(
    id=1, email="super@test.com", user_name="SuperAdmin",
    role_id=ROLE_SUPER_ADMIN, role_label=ROLE_LABELS[ROLE_SUPER_ADMIN],
    subscription_id="sub-001", is_admin=True,
)

MASTER_ADMIN = CurrentUser(
    id=2, email="master@test.com", user_name="MasterAdmin",
    role_id=ROLE_MASTER_ADMIN, role_label=ROLE_LABELS[ROLE_MASTER_ADMIN],
    subscription_id="sub-001", is_admin=True,
)

ORG_ADMIN = CurrentUser(
    id=3, email="orgadmin@test.com", user_name="OrgAdmin",
    role_id=ROLE_ADMIN, role_label=ROLE_LABELS[ROLE_ADMIN],
    subscription_id="sub-001", is_admin=True,
)

USER_RW = CurrentUser(
    id=10, email="user1@test.com", user_name="User1",
    role_id=ROLE_USER, role_label=ROLE_LABELS[ROLE_USER],
    subscription_id="sub-001", is_admin=False,
)

USER_RW_2 = CurrentUser(
    id=11, email="user2@test.com", user_name="User2",
    role_id=ROLE_USER, role_label=ROLE_LABELS[ROLE_USER],
    subscription_id="sub-001", is_admin=False,
)

USER_OTHER_ORG = CurrentUser(
    id=20, email="other@test.com", user_name="OtherOrgUser",
    role_id=ROLE_USER, role_label=ROLE_LABELS[ROLE_USER],
    subscription_id="sub-999", is_admin=False,
)


# ---------- Auth override factory ----------

def _make_auth_override(user: CurrentUser):
    async def _override():
        return user
    return _override


# ---------- Fixtures ----------

@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables before each test, drop after."""
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    # Truncate all tables for next test
    with TEST_ENGINE.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            schema_prefix = f'"{table.schema}".' if table.schema else ""
            try:
                conn.execute(text(f"DELETE FROM {schema_prefix}\"{table.name}\""))
            except Exception:
                pass
        conn.commit()


@pytest.fixture
def db():
    """Provide a test DB session."""
    session = TestSession()
    yield session
    session.close()


@pytest.fixture
def seed_subscriber(db):
    """Seed a UAMSubscriber row for onboarding tests."""
    from core.auth import UAMSubscriber
    sub = UAMSubscriber(
        subscription_id="sub-001",
        name="TestOrg",
        organization="TestOrg Inc",
        active=True,
    )
    db.add(sub)
    db.commit()
    return sub


@pytest.fixture
def seed_uam_users(db):
    """Seed UAMUser rows so group membership validation works."""
    from core.auth import UAMUser
    users = [
        UAMUser(id=USER_RW.id, user_name="User1", email="user1@test.com",
                role=2, subscription_id="sub-001", active=True),
        UAMUser(id=USER_RW_2.id, user_name="User2", email="user2@test.com",
                role=2, subscription_id="sub-001", active=True),
        UAMUser(id=USER_OTHER_ORG.id, user_name="OtherOrgUser", email="other@test.com",
                role=2, subscription_id="sub-999", active=True),
    ]
    for u in users:
        db.merge(u)
    db.commit()
    return users


@pytest.fixture
def seed_org(db):
    """Seed a test org and return it."""
    org = Org(
        subscription_id="sub-001",
        org_name="TestOrg",
        bucket_name="test-bucket",
        region="us-east-1",
        onboarded_by=1,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def seed_admin_folder(db, seed_org):
    """Create an admin folder at org root and return the metadata."""
    meta = FolderMetadata(
        org_id=seed_org.id,
        key="AdminFolder/",
        created_by=SUPER_ADMIN.id,
        created_by_role="admin",
    )
    db.add(meta)
    db.commit()
    db.refresh(meta)
    return meta


@pytest.fixture
def seed_user_folder(db, seed_org):
    """Create a user subfolder under AdminFolder/ and return the metadata."""
    meta = FolderMetadata(
        org_id=seed_org.id,
        key="AdminFolder/UserSub/",
        created_by=USER_RW.id,
        created_by_role="user",
    )
    db.add(meta)
    db.commit()
    db.refresh(meta)
    return meta


@pytest.fixture
def seed_explorer_entry(db):
    """Create a legacy Explorer entry for USER_RW so legacy endpoints work."""
    entry = Explorer(
        user_id=USER_RW.id,
        bucket_name="test-bucket",
        folder_name="TestOrg",
        folder_path="dp-testorg/",
        relative_path="/",
        is_admin=False,
    )
    db.add(entry)
    db.commit()
    return entry


@pytest.fixture
def mock_s3():
    """Provide moto-mocked S3 with test buckets created."""
    with mock_aws():
        conn = boto3.client("s3", region_name="us-east-1")
        conn.create_bucket(Bucket="test-bucket")
        conn.create_bucket(Bucket="test-trash-bucket")
        # Create the admin folder marker in S3
        conn.put_object(Bucket="test-bucket", Key="AdminFolder/", Body=b"")
        yield conn


@pytest_asyncio.fixture
async def client_as(mock_s3, setup_db):
    """
    Factory fixture — returns a function that creates an httpx AsyncClient
    authenticated as the given user.

    Usage:
        async with client_as(SUPER_ADMIN) as c:
            resp = await c.post("/api/v2/explorer/browse/browse", json={...})
    """
    import httpx
    from httpx import ASGITransport
    from main import app
    from api.router import api_router
    from core.config import settings as app_settings
    from contextlib import asynccontextmanager

    # Routes are normally added in the lifespan handler; add them eagerly for tests.
    # Check for a known endpoint (not openapi.json) to avoid double-include.
    _browse_route = f"{app_settings.API_V1_STR}/browse/browse"
    _has_api_routes = any(
        getattr(r, "path", "") == _browse_route
        for r in app.routes
    )
    if not _has_api_routes:
        app.include_router(api_router, prefix=app_settings.API_V1_STR)

    @asynccontextmanager
    async def _factory(user: CurrentUser):
        app.dependency_overrides[get_current_user] = _make_auth_override(user)
        app.dependency_overrides[get_db] = _override_get_db
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
        app.dependency_overrides.clear()

    return _factory
