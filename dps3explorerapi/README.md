# S3 Explorer API

Self-contained backend for S3 Explorer — role-based file management on AWS S3 with owned users/organizations, group grants, 4-eyes approval, and audit logging.

## How It Works

Identity and RBAC live in a single owned Postgres schema (`explorer`). There is no external UAM dependency.

1. **Organizations** bind an `org_key` to an S3 bucket
2. **Users** are owned rows with roles (`admin` / `user` / `master_admin` / `super_admin`)
3. **User Groups** + **Folder Grants** control prefix access
4. **4-Eyes Approval** for sensitive ops (group delete with grants, un-onboard)
5. **Audit Log** in S3 (hot/cold tiers)

### Authentication

Users are provisioned by an administrator and sign in with a verified Google account
whose email matches the provisioned user. The API links that first login to Google's
stable subject and then uses short-lived JWT access and refresh cookies. Cookies are
HttpOnly; unsafe requests must include the readable CSRF cookie value in
`X-CSRF-Token`.

## Local Setup

### Prerequisites

- Docker & Docker Compose (recommended)
- PostgreSQL (empty DB; schema `explorer` is created by Alembic)
- AWS credentials for local S3 access

### Steps

```bash
cd ..

cp .env.example .env
# Fill in: POSTGRES_DATABASE_URI, BUCKET, Google OAuth, S3 keys, SMTP, and bootstrap email

# For direct/non-Compose deployments only:
alembic upgrade head

# Run with Docker Compose (Alembic and the bootstrap super_admin run automatically)
docker compose up --build

# For direct/non-Compose deployments, bootstrap the first super_admin manually:
# python scripts/create_admin.py

# Or run directly
pip install -r dps3explorerapi/requirements.txt
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
| `GOOGLE_CLIENT_ID` | Yes | Google OAuth web client ID |
| `JWT_SECRET_KEY` | Yes | Secret used to sign session JWTs |
| `BACKEND_CORS_ORIGINS` | Yes | Explicit credentialed frontend origins |
| `COOKIE_SECURE` | Production | Set `true` when using HTTPS |
| `COOKIE_SAMESITE` | No | Session cookie SameSite policy |
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
