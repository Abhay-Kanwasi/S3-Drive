# S3 Explorer UI

Standalone Next.js SPA for S3 Explorer — file management, group permissions, and admin workflows.

## How It Works

Fully standalone (no parent iframe). Temporary identity uses a **Dev user selector** that stores a numeric user id and sends it as `X-User-Id` on every API call. Replace with real auth before public deployment.

### Key Flows

- **File Explorer** — browse, upload/download, drag-and-drop, folders, trash
- **Admin Panel** — organizations, users (create/edit role), groups/grants, audit, settings
- **4-Eyes Approval** — group delete / un-onboard confirmation
- **Notifications** — folder access grants and system events

### Role-Based Views

| Role | Access |
|------|--------|
| User | File explorer only |
| Org Admin | Explorer + groups for their org |
| Master/Super Admin | Full admin panel |

## Local Setup

```bash
cd dps3explorerui
cp .env.example .env
# NEXT_PUBLIC_HOSTNAME=http://localhost:8000/api/v2

npm install
npm run dev

# Or from S3-Drive/
cd ..
docker compose up --build
```

UI: `http://localhost:3000/explorer`

### Local authentication

1. Bootstrap an admin via API `scripts/create_admin.py`
2. Open the UI — enter that user id in the **Dev user selector**
3. Requests send `X-User-Id` automatically

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_HOSTNAME` | Backend API base (e.g. `http://localhost:8000/api/v2`) |

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Dev server (port 3000) |
| `npm run build` | Production build |
| `npm start` | Start production server |
| `npm run lint` | ESLint |

## Notes

- `basePath` is `/explorer`
- Group names are free text (no `dp-` prefix)
- Upload/delete/download still use authenticated `/services/*` on the API
