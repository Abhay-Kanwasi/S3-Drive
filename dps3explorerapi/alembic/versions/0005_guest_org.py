"""Seed guest_organization for self-onboarded users.

Revision ID: 0005_guest_org
Revises: 0004_google_auth
Create Date: 2026-09-07
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

from core.config import settings

revision: str = "0005_guest_org"
down_revision: Union[str, Sequence[str], None] = "0004_google_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.execute(text(f"""
INSERT INTO "{SCHEMA}".organizations (org_key, org_name, is_active)
VALUES ('guest_organization', 'Guest Organization', TRUE)
ON CONFLICT (org_key) DO NOTHING
"""))


def downgrade() -> None:
    op.execute(text(f"""
DELETE FROM "{SCHEMA}".organizations WHERE org_key = 'guest_organization'
"""))
