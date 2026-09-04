"""Per-user starred files and folders.

Revision ID: 0002_starred_items
Revises: 0001_initial
Create Date: 2026-09-04
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

from core.config import settings

revision: str = "0002_starred_items"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.execute(text(f"""
CREATE TABLE IF NOT EXISTS "{SCHEMA}".s3_starred_item (
    id         BIGSERIAL    PRIMARY KEY,
    user_id    BIGINT       NOT NULL REFERENCES "{SCHEMA}".users (id),
    org_id     BIGINT       NOT NULL REFERENCES "{SCHEMA}".organizations (id),
    object_key VARCHAR(1024) NOT NULL,
    item_type  VARCHAR(20)  NOT NULL,
    name       VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_star_user_org_key UNIQUE (user_id, org_id, object_key)
)
"""))
    op.execute(text(f"""
CREATE INDEX IF NOT EXISTS ix_s3_starred_item_user_org_created
    ON "{SCHEMA}".s3_starred_item (user_id, org_id, created_at DESC)
"""))


def downgrade() -> None:
    op.execute(text(f'DROP INDEX IF EXISTS "{SCHEMA}".ix_s3_starred_item_user_org_created'))
    op.execute(text(f'DROP TABLE IF EXISTS "{SCHEMA}".s3_starred_item'))
