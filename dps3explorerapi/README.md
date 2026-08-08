# S3 Explorer API

Backend service for S3 Explorer — a role-based file management platform built on AWS S3 with group-based access control, 4-eyes approval workflows, and audit logging.

## How It Works

The API acts as a secure intermediary between the frontend SPA and AWS S3. Users are authenticated via JWT tokens issued by the UAM (User Access Management) system. Access is controlled through organizations, user groups, and folder grants:

1. **Organizations** are onboarded by linking a UAM subscriber to an S3 bucket
2. **User Groups** define collections of users within an org
3. **Folder Grants** map S3 prefixes (folders) to groups with read or read_write access
4. **4-Eyes Approval** enforces dual-approval for sensitive operations (group deletion with grants, org un-onboarding)
5. **Audit Log** records all significant actions to S3 (hot tier: 30 days queryable, cold tier: 365 days archived)

## Local Setup

### Prerequisites

- Docker & Docker Compose
- PostgreSQL database with the `rhymedatapoem` schema
- AWS credentials (access key for local dev)

### Steps

```bash
# 1. Clone and navigate to the project
cd dps3explorerapi

# 2. Create .env from the template
cp .env.example .env
# Fill in: POSTGRES_DATABASE_URI, BUCKET, clientId, clientSecret, tenantId, userId,
#          JWT_SECRET_KEY, AWS credentials, SMTP settings

# 3. Apply database migrations (in order)
psql "$POSTGRES_DATABASE_URI" -f migrations/001_create_org_tables.sql
psql "$POSTGRES_DATABASE_URI" -f migrations/002_create_group_tables.sql
psql "$POSTGRES_DATABASE_URI" -f migrations/003_create_platform_settings.sql
psql "$POSTGRES_DATABASE_URI" -f migrations/004_create_user_notifications.sql
psql "$POSTGRES_DATABASE_URI" -f migrations/005_create_s3_user_deactivation.sql
psql "$POSTGRES_DATABASE_URI" -f migrations/006_create_admin_otp.sql
psql "$POSTGRES_DATABASE_URI" -f migrations/007_create_admin_approval.sql
psql "$POSTGRES_DATABASE_URI" -f migrations/008_group_requires_delete_approval.sql
psql "$POSTGRES_DATABASE_URI" -f migrations/009_create_unonboard_request.sql
psql "$POSTGRES_DATABASE_URI" -f migrations/010_unonboard_delete_org_snapshot.sql
psql "$POSTGRES_DATABASE_URI" -f migrations/011_cleanup_inactive_s3_org.sql

# 4. Run with Docker Compose (from parent directory)
cd ..
docker compose up --build

# Or run directly
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`. Health check: `GET /`

## Production Setup

### Key Differences

| Concern | Local | Production |
|---------|-------|------------|
| AWS credentials | `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` in `.env` | IAM role (EC2/ECS/EKS) — remove AWS keys from env |
| JWT secret | Placeholder value | Strong random secret, rotated periodically |
| SMTP | Office365 app password | Managed secret (AWS Secrets Manager / Vault) |
| Database | Direct connection string | RDS with IAM auth or connection pooler (PgBouncer) |
| `APPROVAL_FRONTEND_URL` | `http://localhost:3000/explorer` | `https://your-domain.com/explorer` |
| Server | `uvicorn --reload` | `uvicorn main:app --workers 4` behind ALB/nginx |

### Running in Production

```bash
# With Docker
docker build -t s3explorer-api .
docker run -p 8000:8000 --env-file .env.prod s3explorer-api

# With ECS/Kubernetes — attach IAM role to task/pod, no AWS keys needed
```

### Scheduled Jobs

The membership cleanup cron removes group memberships for users deactivated beyond the grace period:

```bash
# Run daily via cron
0 2 * * * cd /app && python scripts/cleanup_deactivated_memberships.py

# Or via Kubernetes CronJob
# Dry run first:
python scripts/cleanup_deactivated_memberships.py --dry-run
# Execute:
python scripts/cleanup_deactivated_memberships.py --grace-days 30
```

Grace period is configured via `DEACTIVATION_GRACE_DAYS` env variable (default: 30).

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_DATABASE_URI` | Yes | PostgreSQL connection string |
| `BUCKET` | Yes | Default S3 bucket name |
| `env` | Yes | Environment (`dev` / `prod`) |
| `clientId` | Yes | Azure AD client ID |
| `clientSecret` | Yes | Azure AD client secret |
| `tenantId` | Yes | Azure AD tenant ID |
| `userId` | Yes | Default user ID |
| `JWT_SECRET_KEY` | Yes | Secret for signing JWT tokens |
| `DB_SCHEMA` | No | PostgreSQL schema (default: `datapoem`) |
| `AWS_ACCESS_KEY_ID` | Dev only | Omit in production — use IAM role |
| `AWS_SECRET_ACCESS_KEY` | Dev only | Omit in production — use IAM role |
| `AWS_DEFAULT_REGION` | No | AWS region (default: `us-east-1`) |
| `SMTP_HOST` | No | SMTP server for emails |
| `SMTP_USERNAME` | No | SMTP login |
| `SMTP_PASSWORD` | No | SMTP password |
| `APPROVAL_FRONTEND_URL` | Yes (prod) | Frontend URL for approval email links |
| `DEACTIVATION_GRACE_DAYS` | No | Days before memberships are purged (default: `30`) |

## API Endpoints

Base path: `/api/v2/explorer`

### Services (`/services`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/services/upload-constraints` | Upload rules (extensions, max size) |
| GET | `/services/folders` | List permitted folders |
| POST | `/services/folders` | Create folder |
| POST | `/services/content` | List folder contents |
| POST | `/services/initiate` | Start multipart upload |
| POST | `/services/chunks` | Upload chunk |
| POST | `/services/finalised` | Complete multipart upload |
| POST | `/services/upload/v2` | Single-file upload |
| POST | `/services/delete` | Soft-delete (move to trash) |
| GET | `/services/meta` | File metadata |
| GET | `/services/restore` | Restore from trash |
| GET | `/services/recycle` | List trash |
| GET | `/services/v2/folders` | Integration: register folder access |
| GET | `/services/v2/generate` | Integration: generate upload token |
| POST | `/services/v2/upload` | Integration: token-based upload |

### Browse (`/browse`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/browse/me` | User access status |
| POST | `/browse/browse` | List contents with ownership |
| POST | `/browse/folders/create` | Create folder with ownership |
| POST | `/browse/folders/rename` | Rename folder |
| POST | `/browse/folders/delete` | Delete folder (to trash) |
| POST | `/browse/trash` | List trashed items |
| POST | `/browse/trash/restore` | Restore from trash |
| POST | `/browse/trash/purge` | Permanently delete |

### Admin (`/admin`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/me` | Current admin role and org |
| GET | `/admin/orgs` | List onboarded orgs |
| POST | `/admin/orgs/onboard` | Onboard new org |
| GET | `/admin/available-buckets` | List available S3 buckets |
| GET | `/admin/subscribers` | List UAM subscribers |
| GET | `/admin/settings` | Platform settings |
| PUT | `/admin/settings` | Update platform settings |

### Groups (`/admin`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/admin/groups` | Create group |
| GET | `/admin/groups` | List groups |
| GET | `/admin/groups/{id}` | Group detail |
| PUT | `/admin/groups/{id}` | Rename group |
| DELETE | `/admin/groups/{id}` | Delete group (approval if grants exist) |
| POST | `/admin/groups/{id}/members` | Add members |
| DELETE | `/admin/groups/{id}/members/{user_id}` | Remove member |
| POST | `/admin/groups/{id}/grants` | Add folder grant |
| DELETE | `/admin/groups/{id}/grants/{grant_id}` | Remove grant |
| GET | `/admin/orgs/{org_id}/users` | User search within org |
| GET | `/admin/orgs/{org_id}/folder-tree` | Folder tree for grant UI |

### Users (`/admin`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/users/stats` | Aggregate counts |
| GET | `/admin/users/export` | CSV export |
| GET | `/admin/users` | Paginated user list |
| GET | `/admin/users/{id}` | User detail |
| POST | `/admin/users/{id}/deactivate` | Deactivate S3 access |
| POST | `/admin/users/{id}/reactivate` | Reactivate within grace window |

### Approval & OTP (`/admin`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/otp/approvers` | List eligible approvers |
| POST | `/admin/otp/send` | Send approval email |
| GET | `/admin/approval/review` | Approval review (JSON for SPA) |
| POST | `/admin/approval/respond` | Execute approve/reject |

### Un-onboard (`/admin`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/unonboard/approvers` | List master/super admins |
| POST | `/admin/orgs/{id}/unonboard/send-otp` | Send OTP to requester |
| POST | `/admin/orgs/{id}/unonboard/request` | Submit un-onboard request |

### Other

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/audit` | Paginated audit log |
| GET | `/admin/audit/export` | Audit CSV export |
| GET | `/uam/folders` | User's accessible folders |
| GET | `/uam/items` | Admin nav items |
| GET | `/viewer/preview` | File preview |
| POST | `/files/rename` | Rename file |
| POST | `/files/copy` | Copy file |
| POST | `/files/move` | Move file |
| GET | `/notifications` | User notifications |
| POST | `/notifications/read` | Mark as read |
| DELETE | `/notifications/{id}` | Dismiss notification |

## Project Structure

```
dps3explorerapi/
├── main.py                  # FastAPI app entrypoint
├── requirements.txt         # Python dependencies
├── Dockerfile               # Container build
├── api/
│   ├── router.py            # Mounts all endpoint routers
│   └── endpoints/           # Route handlers (13 files)
├── core/                    # Business logic, auth, config
│   ├── auth.py              # JWT validation, role-based access
│   ├── config.py            # Environment settings
│   ├── approval.py          # 4-eyes approval logic
│   ├── unonboard.py         # Un-onboard logic
│   ├── audit.py             # Audit event recording
│   ├── otp.py               # OTP generation/verification
│   ├── permissions.py       # Grant enforcement
│   └── smtp_email.py        # Email sending
├── db/
│   ├── models.py            # SQLAlchemy ORM models
│   ├── postgresdb.py        # DB session/engine
│   └── boto_core.py         # S3 operations (boto3)
├── migrations/              # SQL migration files (001–011)
├── scripts/
│   └── cleanup_deactivated_memberships.py  # Cron job
├── tests/                   # Pytest test suite (19 files)
└── models/
    ├── request/             # Pydantic request models
    └── email_templates/     # HTML email templates
```

## Testing

```bash
# Run all tests
docker exec dps3explorer-api sh -c 'cd /var/www/python-app && python -m pytest -q'

# Run specific test file
docker exec dps3explorer-api sh -c 'cd /var/www/python-app && python -m pytest tests/test_approval.py -v'
```
