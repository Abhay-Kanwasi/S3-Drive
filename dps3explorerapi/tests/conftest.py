"""
Shared fixtures for S3 Explorer test suite (owned schema, header auth).

Uses:
- SQLite in-memory DB (no real Postgres needed)
- moto-mocked S3 (no real AWS needed)
- FastAPI dependency overrides for auth (no real X-User-Id DB lookup needed)

Run:
    cd dps3explorerapi
    pip install pytest pytest-asyncio httpx moto[s3]
    pytest tests/ -v
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------- Patch env vars BEFORE any app code imports ----------
os.environ["POSTGRES_DATABASE_URI"] = "sqlite:///"
os.environ["BUCKET"] = "test-bucket"
os.environ["env"] = "test"
os.environ["DEV_AUTH_MODE"] = "true"
os.environ["DB_SCHEMA"] = "explorer"
os.environ["TRASH_BUCKET"] = "test-trash-bucket"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

import boto3
import pytest
import pytest_asyncio
from moto import mock_aws
from sqlalchemy import create_engine, event, text, select, func
from sqlalchemy.orm import sessionmaker, Mapper
from sqlalchemy.pool import StaticPool

from core.auth import (
    CurrentUser,
    ROLE_ADMIN,
    ROLE_USER,
    ROLE_MASTER_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_LABELS,
    get_current_user,
)
from db.postgresdb import Base, get_db
from db.models import Organization, User, FolderMetadata

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
    # Schema-qualified tables resolve under the "explorer" alias.
    cursor.execute("ATTACH DATABASE ':memory:' AS explorer")
    cursor.close()


TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


# Per-table id counters — Identity() is a no-op on SQLite attached schemas, and
# max(id)+1 collides when multiple rows flush in one batch.
_ID_COUNTERS: dict[str, int] = {}


@event.listens_for(Mapper, "before_insert")
def _sqlite_assign_identity(mapper, connection, target):
    """SQLite + attached schema does not honor Postgres Identity(); assign ids in tests."""
    if not hasattr(target, "id"):
        return
    table = mapper.local_table
    if "id" not in table.c:
        return
    key = str(table)
    if key not in _ID_COUNTERS:
        current = connection.execute(select(func.coalesce(func.max(table.c.id), 0))).scalar()
        _ID_COUNTERS[key] = int(current or 0)
    explicit = getattr(target, "id", None)
    if explicit is not None:
        _ID_COUNTERS[key] = max(_ID_COUNTERS[key], int(explicit))
        return
    _ID_COUNTERS[key] += 1
    target.id = _ID_COUNTERS[key]


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
    organization_id=1, org_key="org-001", is_admin=True,
)

MASTER_ADMIN = CurrentUser(
    id=2, email="master@test.com", user_name="MasterAdmin",
    role_id=ROLE_MASTER_ADMIN, role_label=ROLE_LABELS[ROLE_MASTER_ADMIN],
    organization_id=1, org_key="org-001", is_admin=True,
)

ORG_ADMIN = CurrentUser(
    id=3, email="orgadmin@test.com", user_name="OrgAdmin",
    role_id=ROLE_ADMIN, role_label=ROLE_LABELS[ROLE_ADMIN],
    organization_id=1, org_key="org-001", is_admin=True,
)

USER_RW = CurrentUser(
    id=10, email="user1@test.com", user_name="User1",
    role_id=ROLE_USER, role_label=ROLE_LABELS[ROLE_USER],
    organization_id=1, org_key="org-001", is_admin=False,
)

USER_RW_2 = CurrentUser(
    id=11, email="user2@test.com", user_name="User2",
    role_id=ROLE_USER, role_label=ROLE_LABELS[ROLE_USER],
    organization_id=1, org_key="org-001", is_admin=False,
)

USER_OTHER_ORG = CurrentUser(
    id=20, email="other@test.com", user_name="OtherOrgUser",
    role_id=ROLE_USER, role_label=ROLE_LABELS[ROLE_USER],
    organization_id=2, org_key="org-999", is_admin=False,
)


def _make_auth_override(user: CurrentUser):
    async def _override():
        return user
    return _override


@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables before each test, drop after."""
    _ID_COUNTERS.clear()
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    with TEST_ENGINE.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            schema_prefix = f'"{table.schema}".' if table.schema else ""
            try:
                conn.execute(text(f'DELETE FROM {schema_prefix}"{table.name}"'))
            except Exception:
                pass
        conn.commit()
    _ID_COUNTERS.clear()


@pytest.fixture
def db():
    session = TestSession()
    yield session
    session.close()


@pytest.fixture
def seed_org(db):
    """Seed a test organization and return it."""
    org = Organization(
        id=1,
        org_key="org-001",
        org_name="TestOrg",
        bucket_name="test-bucket",
        region="us-east-1",
        onboarded_by=None,
        is_active=True,
    )
    db.add(org)
    db.flush()
    # Bootstrap owned users referenced by fixtures
    for u in (
        User(id=1, username="SuperAdmin", email="super@test.com", role=ROLE_SUPER_ADMIN, organization_id=1, active=True),
        User(id=2, username="MasterAdmin", email="master@test.com", role=ROLE_MASTER_ADMIN, organization_id=1, active=True),
        User(id=3, username="OrgAdmin", email="orgadmin@test.com", role=ROLE_ADMIN, organization_id=1, active=True),
        User(id=10, username="User1", email="user1@test.com", role=ROLE_USER, organization_id=1, active=True),
        User(id=11, username="User2", email="user2@test.com", role=ROLE_USER, organization_id=1, active=True),
    ):
        db.merge(u)
    db.flush()  # users must exist before onboarded_by FK is set (org↔user cycle)
    org.onboarded_by = 1
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def seed_other_org(db, seed_org):
    org = Organization(
        id=2,
        org_key="org-999",
        org_name="OtherOrg",
        bucket_name="other-bucket",
        region="us-east-1",
        is_active=True,
    )
    db.add(org)
    db.merge(
        User(
            id=20,
            username="OtherOrgUser",
            email="other@test.com",
            role=ROLE_USER,
            organization_id=2,
            active=True,
        )
    )
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def seed_uam_users(db, seed_org):
    """Compat alias — owned users are seeded with seed_org."""
    return db.query(User).all()


@pytest.fixture
def seed_subscriber(db, seed_org):
    """Compat alias — organizations replace UAM subscribers."""
    return seed_org


@pytest.fixture
def seed_admin_folder(db, seed_org):
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
def mock_s3():
    with mock_aws():
        conn = boto3.client("s3", region_name="us-east-1")
        conn.create_bucket(Bucket="test-bucket")
        conn.create_bucket(Bucket="test-trash-bucket")
        conn.put_object(Bucket="test-bucket", Key="AdminFolder/", Body=b"")
        yield conn


@pytest_asyncio.fixture
async def client_as(mock_s3, setup_db):
    """
    Factory fixture — returns a function that creates an httpx AsyncClient
    authenticated as the given user (dependency override).
    """
    import httpx
    from httpx import ASGITransport
    from main import app
    from api.router import api_router
    from core.config import settings as app_settings
    from contextlib import asynccontextmanager

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
