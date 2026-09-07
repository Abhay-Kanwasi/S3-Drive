# S3 Explorer UI

Standalone Next.js SPA for S3 Explorer — file management, group permissions, and admin workflows.

## How It Works

Fully standalone (no parent iframe). Users sign in with Google; the backend maintains
the authenticated session in HttpOnly cookies.

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

npm install
npm run dev

# Or from S3-Drive/
cd ..
docker compose up --build
```

UI: `http://localhost:3000/explorer`

### Local authentication

1. Bootstrap an admin via API `scripts/create_admin.py`
2. Configure the same Google web client ID in the API and `NEXT_PUBLIC_GOOGLE_CLIENT_ID`
3. Open the UI and sign in with the provisioned Google account

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_HOSTNAME` | Backend API base (e.g. `http://localhost:8000/api/v2`) |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | Google OAuth web client ID |

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
