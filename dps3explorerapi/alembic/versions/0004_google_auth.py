"""Add google_subject to users for Google OAuth login.

Revision ID: 0004_google_auth
Revises: 0003_starred_item_meta
Create Date: 2026-09-05
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

from core.config import settings

revision: str = "0004_google_auth"
down_revision: Union[str, Sequence[str], None] = "0003_starred_item_meta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.execute(text(f"""
ALTER TABLE "{SCHEMA}".users
    ADD COLUMN IF NOT EXISTS google_subject VARCHAR(255)
"""))
    op.execute(text(f"""
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_google_subject
    ON "{SCHEMA}".users (google_subject)
    WHERE google_subject IS NOT NULL
"""))


def downgrade() -> None:
    op.execute(text(f"""
DROP INDEX IF EXISTS "{SCHEMA}".uq_users_google_subject
"""))
    op.execute(text(f"""
ALTER TABLE "{SCHEMA}".users DROP COLUMN IF EXISTS google_subject
"""))
