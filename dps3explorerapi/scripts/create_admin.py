#!/usr/bin/env python3
"""
Idempotent bootstrap of the first super_admin user.

Usage (from dps3explorerapi/):
  python scripts/create_admin.py

Reads:
  BOOTSTRAP_ADMIN_EMAIL    (required)
  BOOTSTRAP_ADMIN_USERNAME (default: admin)

Behavior:
  - If users table is empty: create super_admin with the bootstrap email/username.
  - If a user with that email already exists: upsert role=super_admin and active=True.
  - Otherwise (table non-empty, email missing): create the bootstrap super_admin.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.auth import ROLE_SUPER_ADMIN
from core.config import settings
from db.models import User
from db.postgresdb import Session


def main() -> int:
    email = (settings.BOOTSTRAP_ADMIN_EMAIL or "").strip().lower()
    username = (settings.BOOTSTRAP_ADMIN_USERNAME or "admin").strip() or "admin"

    if not email:
        print("ERROR: BOOTSTRAP_ADMIN_EMAIL is required", file=sys.stderr)
        return 1

    db = Session()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            changed = False
            if existing.role != ROLE_SUPER_ADMIN:
                existing.role = ROLE_SUPER_ADMIN
                changed = True
            if not existing.active:
                existing.active = True
                changed = True
            if username and existing.username != username:
                existing.username = username
                changed = True
            if changed:
                db.commit()
                print(f"Updated existing user id={existing.id} email={email} -> super_admin")
            else:
                print(f"Bootstrap admin already present id={existing.id} email={email}")
            return 0

        user_count = db.query(User).count()
        row = User(
            username=username,
            email=email,
            role=ROLE_SUPER_ADMIN,
            organization_id=None,
            active=True,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        if user_count == 0:
            print(f"Created first super_admin id={row.id} email={email} username={username}")
        else:
            print(f"Created bootstrap super_admin id={row.id} email={email} username={username}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
