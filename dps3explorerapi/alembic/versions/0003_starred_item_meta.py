"""Add size and last_modified to starred items.

Revision ID: 0003_starred_item_meta
Revises: 0002_starred_items
Create Date: 2026-09-04
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

from core.config import settings

revision: str = "0003_starred_item_meta"
down_revision: Union[str, Sequence[str], None] = "0002_starred_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.execute(text(f"""
ALTER TABLE "{SCHEMA}".s3_starred_item
    ADD COLUMN IF NOT EXISTS size VARCHAR(32)
"""))
    op.execute(text(f"""
ALTER TABLE "{SCHEMA}".s3_starred_item
    ADD COLUMN IF NOT EXISTS last_modified VARCHAR(64)
"""))


def downgrade() -> None:
    op.execute(text(f"""
ALTER TABLE "{SCHEMA}".s3_starred_item DROP COLUMN IF EXISTS last_modified
"""))
    op.execute(text(f"""
ALTER TABLE "{SCHEMA}".s3_starred_item DROP COLUMN IF EXISTS size
"""))
