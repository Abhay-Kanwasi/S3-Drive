# S3 Explorer API

Self-contained backend for S3 Explorer — role-based file management on AWS S3 with owned users/organizations, group grants, 4-eyes approval, and audit logging.

## How It Works

Identity and RBAC live in a single owned Postgres schema (`explorer`). There is no external UAM dependency.

1. **Organizations** bind an `org_key` to an S3 bucket
2. **Users** are owned rows with roles (`admin` / `user` / `master_admin` / `super_admin`)
3. **User Groups** + **Folder Grants** control prefix access
4. **4-Eyes Approval** for sensitive ops (group delete with grants, un-onboard)
5. **Audit Log** in S3 (hot/cold tiers)

### Temporary auth (dev)

When `DEV_AUTH_MODE=true` (default), callers send `X-User-Id: <integer>`. This is a stand-in for real auth — replace before any public deployment.

## Local Setup

### Prerequisites

- Docker & Docker Compose (recommended)
- PostgreSQL (empty DB; schema `explorer` is created by Alembic / `scripts/init_db.sql`)
- AWS credentials for local S3 access

### Steps

```bash
cd dps3explorerapi

cp .env.example .env
# Fill in: POSTGRES_DATABASE_URI, BUCKET, AWS keys, SMTP, BOOTSTRAP_ADMIN_EMAIL

# Option A — Alembic baseline
alembic upgrade head

# Option B — raw SQL greenfield script
psql "$POSTGRES_DATABASE_URI" -f scripts/init_db.sql

# Bootstrap first super_admin
python scripts/create_admin.py

# Run with Docker Compose (from S3-Drive/)
cd ..
docker compose up --build

# Or run directly
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API: `http://localhost:8000`  
Health: `GET /api/v2/explorer/health`

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_DATABASE_URI` | Yes | Postgres connection string |
| `BUCKET` | Yes | Default S3 bucket |
| `env` / `ENV` | No | Environment label (default `dev`) |
| `DB_SCHEMA` | No | Schema name (default `explorer`) |
| `DEV_AUTH_MODE` | No | Header auth stand-in (default `true`) |
| `BOOTSTRAP_ADMIN_EMAIL` | For bootstrap | Used by `scripts/create_admin.py` |
| `BOOTSTRAP_ADMIN_USERNAME` | No | Default `admin` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Dev only | Omit in prod — use IAM role |
| `SMTP_*` / `APPROVAL_*` | For email flows | OTP / approval links |

## Testing

```bash
pip install pytest pytest-asyncio httpx 'moto[s3]'
pytest tests/ -q
```

Or via Docker:

```bash
docker exec dps3explorer-api sh -c 'cd /var/www/python-app && python -m pytest -q'
```

## Notes

- Authenticated `/services/*` file ops are the real upload/delete/download/trash backend — keep them.
- Unauthenticated `/services/v2/*` token routes are intentionally stubbed (501).
- Legacy SQL under `archive/migrations/` is reference-only (old `rhymedatapoem` schema).
