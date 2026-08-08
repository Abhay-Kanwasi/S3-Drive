# S3 Explorer UI

Frontend SPA for S3 Explorer — a file management platform with role-based access, group permissions, and admin workflows. Built with Next.js 14 (App Router), React 18, Tailwind CSS, and React Query.

## How It Works

The UI is embedded as an iframe within the DataPoem parent application. Authentication flows via `postMessage` from the parent app, passing the user's JWT token and identity. For standalone access (local dev), tokens are set directly in `localStorage`.

### Key Flows

- **File Explorer** — Browse S3 folders, upload/download files, drag-and-drop, create folders, rename, delete (soft-delete to trash), restore from trash
- **Admin Panel** — Manage organizations, user groups, folder grants, view users, audit logs, platform settings
- **4-Eyes Approval** — Slide-out sidebar panels for group delete and un-onboard flows with approver selection and email-based confirmation
- **Notifications** — Real-time notification bell for folder access grants and system events

### Role-Based Views

| Role | Access |
|------|--------|
| User | File explorer only |
| Org Admin | Explorer + Groups management for their org |
| Master/Super Admin | Full admin panel including Buckets, Users, Un-onboard, Settings |

## Local Setup

### Prerequisites

- Node.js 20+
- Docker & Docker Compose (recommended)
- Backend API running on port 8000

### Steps

```bash
# 1. Navigate to the UI directory
cd dps3explorerui

# 2. Create .env
echo "NEXT_PUBLIC_HOSTNAME=http://localhost:8000/api/v1" > .env

# 3. Install and run
npm install
npm run dev

# Or with Docker Compose (from parent directory)
cd ..
docker compose up --build
```

The UI will be available at `http://localhost:3000/explorer`

### Local Authentication

Since there's no parent app in local dev, set the token manually in browser console:

```javascript
localStorage.setItem("authToken", "<your-jwt-token>"); location.reload();
```

## Production Setup

### Environment Variables

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_HOSTNAME` | Backend API base URL (e.g. `https://api.datapoem.ai/api/v1`) |
| `NEXT_PUBLIC_PARENT_APP_URL` | Parent app URL for auth redirect (e.g. `https://app.datapoem.ai`) |

### Deployment

```bash
# Build production image
docker build -t s3explorer-ui .
docker run -p 80:80 s3explorer-ui

# Or build and export
npm run build
npm start -- --port 80
```

### Key Production Config

- **`basePath: '/explorer'`** — all routes served under `/explorer/*`
- **CSP frame-ancestors** — restricts iframe embedding to DataPoem domains
- **Auth via postMessage** — parent app sends `AUTH_USER_DATA` with JWT token
- **No AWS credentials needed** — UI only talks to the backend API

## Available Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start dev server (port 3000) with hot reload |
| `npm run build` | Production build |
| `npm start` | Start production server |
| `npm run lint` | Run ESLint |

## Project Structure

```
dps3explorerui/
├── next.config.mjs          # basePath, CSP headers
├── tailwind.config.js       # Tailwind theme/colors
├── package.json             # Dependencies and scripts
├── Dockerfile               # Production container (Node 20, port 80)
├── .env                     # NEXT_PUBLIC_HOSTNAME
├── src/
│   ├── app/
│   │   ├── layout.js        # Root layout with providers
│   │   ├── page.js          # Landing/redirect
│   │   ├── globals.css      # Tailwind + custom animations
│   │   ├── explorer/        # File explorer pages
│   │   │   ├── layout.js    # Auth, access checks, drag-and-drop
│   │   │   ├── content.js   # Main content area
│   │   │   ├── sidebar.js   # Folder tree sidebar
│   │   │   ├── header.js    # Top bar
│   │   │   └── page.js      # Explorer root
│   │   ├── admin/           # Admin panel
│   │   │   ├── layout.js    # Admin nav sidebar + access gating
│   │   │   ├── page.js      # Buckets/orgs (master admin)
│   │   │   ├── UnonboardModal.js  # Un-onboard sidebar panel
│   │   │   ├── approval/    # 4-eyes approval confirmation
│   │   │   ├── groups/      # Group management + delete panel
│   │   │   ├── users/       # User list + deactivation
│   │   │   ├── audit/       # Audit log viewer
│   │   │   └── settings/    # Platform settings
│   │   └── api/health/      # Next.js API health route
│   ├── components/           # Reusable UI components
│   │   ├── NotificationBell.js   # Notification dropdown
│   │   ├── FileViewerModal.js    # File preview modal
│   │   ├── FolderPickerModal.js  # Folder selection for copy/move
│   │   ├── upload.js             # Upload with progress
│   │   ├── cards.js / list.js    # Grid/list file views
│   │   ├── trash.js              # Trash/recycle UI
│   │   └── ...
│   └── services/             # API clients and state
│       ├── ContextProvider.js    # Global React context
│       ├── QueryProvider.js      # React Query setup
│       ├── admin.js              # Admin API calls
│       ├── browse.js             # Browse/folder API calls
│       ├── notifications.js      # Notification API calls
│       ├── access.js             # Access check helpers
│       └── server.js             # Generic fetch wrapper
└── public/                   # Static assets
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 14 (App Router) |
| UI | React 18, Tailwind CSS |
| State | React Query 3, React Context |
| Icons | Lucide React |
| Styling | Tailwind + custom CSS animations |
| Build | Webpack (via Next.js) |
| Container | Node 20 (Bitnami) |
