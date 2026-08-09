---
name: Independent dps3explorer
overview: Decouple dps3explorer from the external UAM Postgres and JWT by giving it its own single-schema database (owned users/organizations/roles + existing S3 RBAC tables), an in-app admin user/role management surface, a temporary header-based identity stand-in, and full removal of datapoem/rhymedatapoem coupling across API and UI. Legacy tables and unauthenticated integration routes are dropped.
todos:
  - id: schema-models
    content: Add User/Organization models, repoint FKs, delete legacy + s3_org, set DB_SCHEMA=explorer in db/models.py and core/config.py
    status: completed
  - id: alembic-baseline
    content: Configure alembic/env.py for owned schema and write 0001_initial baseline creating all tables + platform_settings singleton; add scripts/create_admin.py bootstrap
    status: completed
  - id: core-auth
    content: Rewrite core/auth.py to X-User-Id identity, update core/user_access.py and core/permissions.py (drop s3_explorer fallback)
    status: completed
  - id: endpoints
    content: Update users.py (CRUD+roles), admin.py (organizations), groups.py, browse.py and all endpoints to new get_current_user; remove only `/services/v2/*` token routes and `/uam/folders` after legacy-access transformation, while keeping authenticated `/services/*`
    status: completed
  - id: tests
    content: Replace UAM fixtures with owned users/orgs, header-based auth override, schema explorer in tests/conftest.py and modules
    status: completed
  - id: ui-auth
    content: Replace serviceToken cookie/postMessage with X-User-Id + dev user selector; update all src/services/*.js clients; remove legacy/org-less branches
    status: completed
  - id: ui-admin
    content: Add Create User + Edit Role UI, owned organizations onboarding, rework status strings, remove parent-app redirect
    status: completed
  - id: branding-sweep
    content: Remove/parameterize all datapoem/rhymedatapoem references across API+UI+CI+docs; verify with repo-wide grep returning zero
    status: completed
  - id: env-docs
    content: Add backend and frontend .env.example, update READMEs, document bootstrap + migration steps
    status: completed
isProject: false
---

# Make dps3explorer a Self-Contained, Independent Application

## Confirmed decisions

- Organization model: MERGE into a single owned `organizations` table (chosen as the simplest option). Tradeoff: we lose the separation between "tenant catalog" (`subscriber`) and "onboarded bucket binding" (`s3_org`). Mitigation: keep the onboarding-specific columns that `s3_org` actually has today (`bucket_name`, `region`, `max_upload_size_bytes`, `onboarded_by`, `is_active` — note there is NO `prefix` column) on `organizations`; a row exists only once an org is onboarded. If a future need arises to list non-onboarded tenants, add an `onboarded` boolean rather than re-splitting.
- Legacy tables/paths: DROP the legacy DATA tables and the UAM/legacy-coupled paths — `s3_explorer`, `s3_explorer_logs`, `s3_access`, the `s3_explorer` permission fallback (`core/permissions.py`), and the unauthenticated `/services/v2/*` token-integration routes that use `s3_access`/`Explorer` (`boto_services.py`).
- IMPORTANT — do NOT drop the authenticated `/services/*` file-operation routes. These (`/services/initiate`, `/chunks`, `/finalised`, `/delete`, `/download`, `/recycle`, `/restore`, `/upload-constraints`, `/meta`, `/content`, `/folders`, `/event`) are the REAL, currently-used upload/delete/download/trash backend consumed by `dps3explorerui/src/services/server.js`. The `/files/*` router only covers rename/copy/move (`api/endpoints/files.py:1-7`). Keep `/services/*`, just decouple them from UAM/legacy and replace the hardcoded `user_id: 0` / `userid: "0"` sentinels with the real current user.
- Group naming: REMOVE the `dp-` prefix convention entirely. Group names become neutral, user-supplied names with no mandatory prefix. This applies to API validation, admin UI create/rename flows, and legacy-migration-created groups. The legacy migration group from 2.6 step 3c becomes `legacy-user-{user_id}` (no `dp-`).
- UI: FULLY STANDALONE — remove iframe/postMessage/parent-app redirect; identity via a temporary dev user selector that sends `X-User-Id` (clearly marked as a stand-in for real auth).
- Single schema name: `explorer` (replaces both `datapoem` and `rhymedatapoem`).
- S3 stays the file/data backend (unchanged).

---

## 1. Target architecture (before vs after)

### Before

```mermaid
flowchart LR
  UI[dps3explorerui Next.js] -->|Bearer serviceToken cookie| API[dps3explorerapi FastAPI]
  API -->|decode HS256 JWT| API
  API -->|read users/orgs/modules| UAM[(External UAM Postgres\nuser_data, subscriber, modules)]
  API -->|owned RBAC + legacy| DB[(Same DB\nrhymedatapoem + datapoem schemas)]
  API --> S3[(AWS S3)]
```

### After

```mermaid
flowchart LR
  UI[dps3explorerui Next.js standalone] -->|X-User-Id header| API[dps3explorerapi FastAPI]
  API -->|owned identity + RBAC| DB[(Owned Postgres\nsingle 'explorer' schema)]
  API --> S3[(AWS S3)]
```

Key change: `core/auth.py` no longer decodes an external JWT or queries `user_data`/`subscriber`/`modules`/`user_data_modules`. `get_current_user` resolves the caller from an owned `users` table via `X-User-Id`. `require_role(...)` and `core/permissions.py` read role/permissions from owned tables. Every table lives in one `explorer` schema. No UAM, no legacy tables.

---

## 2. Complete database schema (owned, single `explorer` schema)

### 2.1 Role model

Keep an integer enum column on `users` (no separate `roles`/`permissions` tables for now — matches "no new RBAC engine"). Mapping preserved from current code (`core/auth.py`):

- `1 = admin` (org-scoped admin)
- `2 = user`
- `3 = master_admin` (global)
- `4 = super_admin` (global)

`super_admin` and `master_admin` are both treated as global admins (as today). `admin` is org-scoped. Store as `SMALLINT` with a `CHECK (role IN (1,2,3,4))`. (Role `5 = AGENCY_HEAD` appears only in `PLAN.md`, never in code — excluded; note as open question.)

### 2.2 Identity tables (replace UAM)

organizations (replaces `subscriber` + folds in `s3_org`). IMPORTANT: keep every column the current `s3_org` model exposes so runtime behavior does not regress (`db/models.py:24-41`):
- `id` BIGSERIAL PK
- `org_key` VARCHAR UNIQUE NOT NULL — stable external identifier, backfills old `s3_org.subscription_id`
- `name` VARCHAR NOT NULL — maps to current `org_name`
- `bucket_name` VARCHAR UNIQUE NULL — onboarded S3 bucket
- `region` VARCHAR NOT NULL DEFAULT 'us-east-1'
- `max_upload_size_bytes` BIGINT NOT NULL DEFAULT 5368709120 — per-org upload cap, used in `boto_services.py` and PLAN; DO NOT drop
- `onboarded_by` BIGINT NULL REFERENCES users(id) — used by OTP approver resolution (`core/otp.py:56-66`); DO NOT drop
- `active` BOOLEAN NOT NULL DEFAULT true — maps to current `is_active`
- `onboarded_at` TIMESTAMPTZ NULL
- `created_at` / `updated_at` TIMESTAMPTZ NOT NULL DEFAULT now()

Naming note: current code uses `Org.org_name`, `Org.is_active`, `Org.subscription_id`. Renaming to `name`/`active`/`org_key` is a code-wide refactor across `admin.py`, `browse.py`, `files.py`, `groups.py`, `otp.py`, `unonboard.py`. To minimize churn, the implementer may instead KEEP the existing column names (`org_name`, `is_active`, `subscription_id`) on the new `organizations` table and only add the FK/identity changes. Decide once and be consistent (open question 6).

users (replaces `user_data`):
- `id` BIGSERIAL PK
- `username` VARCHAR NOT NULL
- `email` VARCHAR UNIQUE NOT NULL
- `role` SMALLINT NOT NULL DEFAULT 2, CHECK (role IN (1,2,3,4))
- `organization_id` BIGINT NULL REFERENCES organizations(id) ON DELETE SET NULL
- `active` BOOLEAN NOT NULL DEFAULT true — account-level (replaces `user_data.active`)
- `created_at` / `updated_at` TIMESTAMPTZ NOT NULL DEFAULT now()
- Indexes: `ix_users_email` (unique), `ix_users_organization_id`, `ix_users_role`

Deactivation: keep the two SEPARATE layers — do NOT collapse them into one action. This mirrors current behavior where account status and Explorer access are distinct (`core/user_access.py:37-39`, `api/endpoints/users.py:8-9`, and the two-state UI badges at `admin/users/page.js:159-175`).
- `users.active` = account-level enable/disable (replaces the former UAM `user_data.active`). Written by a new account-management action (global admins).
- `s3_user_deactivation` (existing table, unchanged) = Explorer-access-only deactivation with the 30-day grace/reactivation window.
- Effective access stays `effective_s3_access(account_active, s3_deactivated)` in `core/user_access.py`; only the source of `account_active` changes from UAM to owned `users.active`.
- UI status strings change from "Inactive (UAM)" to "Inactive (account)"; "Inactive (S3 Explorer)" stays.

Module entitlement (`modules` / `user_data_modules`): DROP. The admin user-list filter that hid non–Data Hub users is removed; instead the list shows all owned users. Note in cutover.

### 2.3 App-owned S3 RBAC tables (kept, re-homed to `explorer`, FKs repointed)

All from `db/models.py`, now under `explorer`:
- `s3_folder_metadata`
- `s3_user_group`, `s3_group_membership`, `s3_folder_grant`
  - `s3_group_membership.user_id` -> FK `users(id)`
  - `s3_user_group.org_id` and `s3_folder_grant.org_id` -> FK `organizations(id)`
- `s3_user_deactivation.user_id` -> FK `users(id)`
- `s3_admin_otp`, `s3_admin_approval`, `s3_unonboard_request` (approver/requester ids -> `users(id)`)
  - `s3_unonboard_request.org_id` -> FK `organizations(id)` (ON DELETE SET NULL, as today). Its `subscription_id`/`org_name`/`bucket_name` columns are point-in-time SNAPSHOTS (`db/models.py:159-161`) — keep them as plain snapshot strings, do NOT convert to FKs.
- `s3_user_notification.user_id` -> FK `users(id)`
- `s3_platform_settings` (singleton, seeded)

Dropped entirely: `s3_org` (merged into `organizations`), `s3_explorer`, `s3_explorer_logs`, `s3_access`.

### 2.4 ERD (target)

```mermaid
erDiagram
  organizations ||--o{ users : has
  organizations ||--o{ s3_user_group : owns
  users ||--o{ s3_group_membership : joins
  s3_user_group ||--o{ s3_group_membership : contains
  s3_user_group ||--o{ s3_folder_grant : grants
  users ||--o{ s3_user_notification : receives
  users ||--o{ s3_user_deactivation : deactivated
  s3_user_group ||--o{ s3_unonboard_request : requests
  organizations ||--o{ s3_folder_metadata : contains
```

### 2.5 Migration strategy

Adopt Alembic as the single source of truth (infra already exists: `alembic.ini`, `alembic/env.py`; `alembic/versions/` empty). Retire the 11 raw SQL files.

- `env.py`: set `version_table_schema` and `include_schemas=True`; read schema from `settings.DB_SCHEMA`; `CREATE SCHEMA IF NOT EXISTS`.
- One baseline revision `0001_initial` that creates the schema + ALL tables/columns/PK/FK/unique/indexes/defaults for the target model above, so a fresh empty DB boots ready.
- Seed only singletons: insert `s3_platform_settings` row 1 (preserve current behavior from `003_create_platform_settings.sql`).
- Bootstrap admin (see 3.4): a separate idempotent revision `0002_seed_bootstrap_admin` OR a `scripts/create_admin.py` CLI (recommended: CLI, so empty-DB requirement holds and first admin is created explicitly from env vars `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_USERNAME`).
- Keep the old `migrations/*.sql` in an `archive/` folder for reference or delete (open question).
- Update `tests/conftest.py` (currently `ATTACH ... AS rhymedatapoem`, `DB_SCHEMA=main`) to build the owned schema via metadata create_all with schema `explorer`.

### 2.6 Two delivery paths (must pick per environment)

This plan primarily specifies a GREENFIELD empty DB (the prompt's requirement). Production has live data in the shared UAM DB, so a separate CUTOVER path is required — the greenfield migrations alone will not preserve existing orgs/groups/grants.

- Greenfield (fresh install): run `0001_initial` + platform-settings singleton + `scripts/create_admin.py`. Ready to use.
- Production cutover (data migration): a one-time backfill script/revision that, within a maintenance window:
  1. Copies `subscriber` rows for all active onboarded orgs into `organizations` first (so `organization_id` FKs resolve), mapping `subscription_id -> org_key`, `organization_name -> name`, carrying `bucket_name`, `region`, `max_upload_size_bytes`, `onboarded_by`, `is_active`.
  2. Copies USERS into owned `users`, preserving `id`. Copy the UNION of:
     a. every user referenced by RBAC/workflow rows (group memberships `user_id`, `folder_grant.created_by`, `folder_metadata.created_by`, `s3_org.onboarded_by`, notifications, deactivations, approval/otp/unonboard requester+approver), AND
     b. every eligible member of each onboarded org — i.e. the same population the admin user list shows today: UAM users whose `subscription_id` is in the onboarded set AND who have the Data Hub module (`users.py:61-76`). This prevents an empty/partial admin user list and broken user pickers on day one. If the Data Hub module filter is being dropped going forward, copy all users of onboarded orgs regardless of module.
     Set `users.role` from UAM `user_data.role`, `users.active` from `user_data.active`, `organization_id` from the org mapped in step 1.
  3. Legacy `s3_explorer` access transformation (MANDATORY before dropping the table and the fallback): for each distinct `(user_id, bucket_name, relative_path, folder_path, is_admin)` in `s3_explorer`, resolve the owned org by bucket, then create equivalent owned access using a DETERMINISTIC mapping rule:
     a. Normalize the legacy prefix to grant as: use `relative_path` if non-empty; otherwise use `folder_path`; trim leading `/`; ensure folders end with `/`; map blank/root to `""`.
     b. Access level mapping: `is_admin = true` -> `read_write`; `is_admin = false` -> `read`.
     c. Group mapping: create or reuse a stable per-user legacy migration group inside the owned org, named `legacy-user-{user_id}` (no `dp-` prefix). The `org_id` scoping is already provided by the group's `org_id` + the `uq_group_org_name` unique constraint, so it need not be in the name. Then add exactly one `s3_group_membership` for that user/group pair. These migration groups are normal, admin-visible groups (not hidden).
     d. Grant mapping: for each normalized prefix, create one `s3_folder_grant` on that legacy group with the mapped access level; dedupe identical `(group_id, prefix)` grants.
     e. Validation: compare each user's pre-cutover visible orgs/prefixes from `s3_explorer` + grants with the post-cutover prefixes from owned groups/grants. Users with legacy-only access MUST end up with equivalent or broader owned access, otherwise they lose access when `_user_has_legacy_access` (`core/permissions.py:53-55,78-80`) and `/uam/folders` (`uam_services.py:24-59`) are removed. Explicitly list any users you intentionally drop.
  4. Repoints `s3_*` tables to the owned schema (rename schema / move tables) with FKs to `users`/`organizations`.
  5. Verifies row counts, that every referenced `user_id`/`org_id` resolves, and that no user who had legacy or grant access loses it, before flipping `DB_SCHEMA` and removing UAM access.
- Preserving existing integer ids is REQUIRED because current tables store bare integer `user_id`/`created_by`/`onboarded_by` values (e.g. `db/models.py:52,94,117,133`), not real FKs — a re-id would orphan grants and memberships.
- Sequencing: for a production cutover, the `s3_explorer` fallback and `/uam/folders` route must NOT be removed until step 3 has run and been verified. In greenfield there is no legacy data, so the fallback/route are removed immediately.

---

## 3. User/role/permission management (in-app, replaces UAM)

### 3.1 Data model reuse

Authorization keeps using the existing gate `require_role([...])` (`core/auth.py`) and folder-grant checks in `core/permissions.py`, but both now read `role`/membership/grants from owned `users` + existing group/grant tables. No new RBAC engine.

### 3.2 New/changed admin endpoints (under `/api/v2/explorer/admin`)

- `POST /admin/users` — create user (username, email, role, organization_id, active). NEW.
- `GET /admin/users` — list users (owned table; drop module filter). CHANGED.
- `GET /admin/users/{id}` — detail. CHANGED (owned source).
- `PATCH /admin/users/{id}` — edit username/email/role/organization. NEW (role assignment/change lives here).
- Keep the two deactivation layers as distinct endpoints (do not merge):
  - `POST /admin/users/{id}/deactivate` and `/reactivate` — Explorer-access only (existing `s3_user_deactivation` + 30-day grace). Behavior preserved; only the underlying user source changes. CHANGED.
  - `POST /admin/users/{id}/account/deactivate` and `/account/reactivate` — account-level (`users.active`), global admins only. NEW (replaces what UAM used to own).
- Org endpoints: replace `GET /admin/subscribers` (UAM) with `GET /admin/organizations` and `POST /admin/organizations` (create/onboard by binding bucket). CHANGED `admin.py`.
- Group member pickers: `groups.py` member validation/search now queries owned `users` instead of `UAMUser`.

Authorization: create/edit/role-change restricted to global admins (`master_admin`/`super_admin`); org admins limited to their `organization_id`.

### 3.3 "Current user" stand-in (temporary)

Remove JWT decode. New `get_current_user` dependency:
- Reads `X-User-Id` header (integer) -> loads owned `users` row -> builds `CurrentUser` (id, email, username, role_label, organization_id).
- If header missing/invalid/inactive -> 401.
- Gate behind `settings.DEV_AUTH_MODE` (default true) with a prominent docstring/log: TEMPORARY stand-in, replace with real auth later. Anyone who can set the header can impersonate — acceptable only for internal/dev.

### 3.4 Bootstrap

`scripts/create_admin.py` (idempotent): creates one `super_admin` user from env if the `users` table is empty. Documented in README as the first step after migrations.

---

## 4. Datapoem / rhymedatapoem removal inventory

Replacement rules:
- DB schema name `datapoem` / `rhymedatapoem` -> `explorer` (single).
- Product branding "DataPoem" -> neutral "Explorer" / configurable.
- Production domains/emails/CI cluster names -> env-driven placeholders (NOT hardcoded).

### API (schema/code)
- `core/config.py:38` `DB_SCHEMA` default `datapoem` -> `explorer`.
- `db/models.py:4,210,223,235` comment + 3 legacy `__table_args__` -> legacy models deleted (dropping legacy tables).
- `migrations/001..011*.sql` (all hardcode `rhymedatapoem`) -> removed; replaced by Alembic baseline using `settings.DB_SCHEMA`.
- `core/auth.py:5` docstring `datapoem.user_data` -> updated.
- `.env:1,19` -> owned DB URI + `DB_SCHEMA=explorer`.
- `tests/conftest.py:76,78` `rhymedatapoem` attach -> `explorer`.
- `README.md:20,110`, `PLAN.md`, `s3_explorer_feature_build_*.plan.md` -> docs updated.

### UI (branding/copy — no `rhymedatapoem` in UI tree)
- `src/services/auth.js:1` UAM cookie comment -> removed (cookie auth replaced).
- `src/app/admin/approval/page.js:118,127` "Sign in to DataPoem" -> neutral copy.
- `src/app/explorer/header.js:9` `alt="DataPoem logo"` -> neutral.
- `README.md:7,62,63,80` -> updated.
- `next.config.mjs:17` CSP `frame-ancestors` datapoem domains -> env-driven / removed (standalone).
- `src/app/explorer/layout.js:143-148` postMessage origin allowlist -> removed (standalone).
- `.github/workflows/*.yml`, `docker-compose.yml`, email templates (`models/email_templates/notification.py:16,85`), SMTP sender (`.env:23`), `tailwind.config.js` `dp-*` tokens, `package.json` name `s3_explorer_v2` -> parameterize or rename. Also REMOVE the mandatory `dp-` group-name prefix from `groups/page.js`, `groups/[id]/page.js`, and any backend validation/comments that enforce it.

### Verification
- Repo-wide `rg -i 'rhymedatapoem'` -> 0 matches (hard requirement).
- Repo-wide `rg -i 'datapoem'` -> only remaining hits are intentional env-placeholder examples or explicitly-approved deployment values; otherwise 0.

---

## 5. File-by-file change list

### Backend (`dps3explorerapi`)

- `core/auth.py` — remove JWT decode + `UAMUser/UAMSubscriber/UAMModule/UAMUserModule` ORM; new `X-User-Id` `get_current_user`; keep `require_role`; role labels unchanged.
- `core/user_access.py` — read owned `users.active` instead of UAM; keep `s3_user_deactivation` layer.
- `core/permissions.py` — remove `s3_explorer` fallback (lines ~53-56, 78-84); grants come solely from owned tables.
- `core/config.py` — `DB_SCHEMA` default `explorer`; remove `JWT_*` and `MONGO_*`; convert the mandatory Azure reads `config_env["clientId"/"clientSecret"/"tenantId"/"userId"]` to optional `.get(...)` (they currently crash boot if unset and are otherwise unused); keep `BUCKET`, SMTP, and `APPROVAL_*`; add `DEV_AUTH_MODE`, bootstrap admin vars.
- `core/otp.py`, `core/unonboard.py`, `core/approval.py`, `core/approval_requester_notify.py` — approver/requester/display lookups via owned `users`.
- `core/audit.py` — unchanged (S3-only); confirm it still enriches names via owned `users`.
- `core/utils.py` — remove legacy `Explorer` helpers.
- `db/models.py` — delete legacy models (`Explorer`, `ExplorerAction`, `s3_access`); delete `s3_org` model (merge into new `Organization`); add `User`, `Organization`; repoint FKs; all `SCHEMA = settings.DB_SCHEMA`. Remove the stale `dp-` group-name convention comment from `UserGroup`.
- `db/postgresdb.py` — unchanged (session factory).
- `api/endpoints/admin.py` — replace subscriber onboarding with owned `organizations` create/onboard.
- `api/endpoints/users.py` — full rewrite of query layer to owned `users`; add create/edit/role-assign; drop module filter.
- `api/endpoints/groups.py` — member validation/search via owned `users`; remove enforced `dp-` prefix logic from create/rename validation and responses.
- `api/endpoints/browse.py` — `/browse/me` builds identity from `X-User-Id`; trash metadata via owned users.
- `api/endpoints/uam_services.py` — remove legacy `/uam/folders` (depends on `s3_explorer`); decide whether `/uam/items` menu probe is replaced by an owned `/admin/me` flag (recommended) — rename router away from "uam".
- `api/endpoints/boto_services.py` — remove ONLY the unauthenticated `/services/v2/*` token routes + `s3_access`/`Explorer` usage and the legacy `_resolve_bucket`/`Explorer` bucket lookups. KEEP the authenticated `/services/*` file-op routes (upload/delete/download/trash/etc.) — they are the working backend; de-couple them from UAM, drop `user_id: 0` sentinels, resolve org/bucket via owned `organizations`. Note upload uses `settings.BUCKET` today (`boto_services.py:397,409,414,427`) — keep that env name unless a rename is explicitly scoped.
- `api/endpoints/viewer.py`, `files.py`, `notifications.py`, `otp.py`, `approval.py`, `unonboard.py`, `audit.py` — swap to new `get_current_user`; no UAM.
- `alembic/env.py` + new `alembic/versions/0001_initial.py` — baseline schema.
- `scripts/create_admin.py` — bootstrap.
- `migrations/*.sql` — remove/archive.
- `tests/*` (conftest + ~19 modules) — replace UAM fixtures with owned users/orgs; new header-based auth override; schema `explorer`.

### Frontend (`dps3explorerui`)

- `src/services/auth.js` — remove `serviceToken` cookie reader; add temp user-id source (dev selector value).
- `src/services/ContextProvider.js` — replace `authToken` state with `currentUserId`.
- `src/services/server.js`, `browse.js`, `access.js`, `admin.js`, `notifications.js` — replace `Authorization: Bearer ${serviceToken}` header with `X-User-Id` in `authHeaders()`/`getAuthHeaders()` (`server.js:7-13`, `browse.js:6-12`). KEEP the `/services/*` upload/delete/download/trash calls (they remain the backend), but replace the hardcoded `user_id: 0` / `userid: "0"` payloads (`server.js:60,78,96,118,146,229`) with the selected user id. Drop only `getUAMFolderContent` -> `/uam/folders` (`server.js:22-30`).
- `src/app/explorer/layout.js` — remove postMessage/localStorage `userData` and `/uam/items` probe; add a dev user selector; gate explorer on selected user; use owned `/admin/me` (or `/browse/me`) for admin flag.
- `src/app/admin/layout.js`, `AdminContext.js` — admin gate via owned `/admin/me`.
- `src/app/admin/approval/page.js` — remove parent-app redirect / "Sign in to DataPoem"; use selected user.
- `src/app/admin/page.js` — onboarding wizard uses owned `/admin/organizations` instead of `/admin/subscribers` + `subscription_id`.
- `src/app/admin/users/page.js` — add Create User + Edit Role UI; rework status strings (drop "Inactive (UAM)"); keep S3 deactivation actions.
- `src/app/admin/groups/page.js`, `groups/[id]/page.js` — remove the hardcoded `dp-` prefix UI, create/rename helper text, and any client-side prefix stripping/appending. Group names become neutral free-text names.
- `src/components/*` (`bucket.js`, `newfolder.js`, `view.js`, `trash.js`, `upload.js`, `delete.js`, `context.js`, `UserPicker.js`, `S3ExplorerAccessBlocked.js`) — remove legacy/org-less branches; user picker searches owned users; access-blocked reasons drop `uam`.
- `next.config.mjs` — remove/parameterize CSP frame-ancestors; keep `basePath` decision (standalone).
- Branding: `header.js`, `README.md`, `tailwind.config.js`, `package.json`, workflows — neutralized/parameterized.

---

## 6. Config / env changes + `.env.example`

Backend `.env.example` (NEW, referenced by `README.md:30`):

IMPORTANT: variable names below MUST match what `core/config.py` actually reads today, or the code must be refactored in the same change. Current names are `BUCKET`, `env`, `SMTP_USERNAME`, `SMTP_PASSWORD`; and `clientId/clientSecret/tenantId/userId` are read with `config_env[...]` (no default) so the app fails to boot if they are absent (`core/config.py:27-34,47-51`).

```dotenv
# Database (owned)
POSTGRES_DATABASE_URI=postgresql+psycopg2://user:pass@localhost:5432/explorer
DB_SCHEMA=explorer

# Temporary auth stand-in (replace with real auth later)
DEV_AUTH_MODE=true

# Bootstrap first admin (used by scripts/create_admin.py)
BOOTSTRAP_ADMIN_EMAIL=admin@example.com
BOOTSTRAP_ADMIN_USERNAME=admin

# AWS / S3 (core backend). NOTE: current code reads BUCKET (not S3_BUCKET).
BUCKET=
TRASH_BUCKET=explorer-trash
AUDIT_BUCKET=explorer-trash
env=local

# Azure AD vars are currently REQUIRED at import (config_env["clientId"], etc.).
# Either provide them, OR (recommended) make them optional in core/config.py as part of this work.
clientId=
clientSecret=
tenantId=
userId=

# SMTP (notifications/OTP/approval) — names must stay SMTP_USERNAME/SMTP_PASSWORD
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=support@example.com

# Approval email links — keep this; approval.py warns and degrades without it
APPROVAL_FRONTEND_URL=
APPROVAL_BASE_URL=
```

Removed/deprecated: `JWT_SECRET_KEY`, `JWT_ALGORITHM` (`core/config.py:36-37`), `MONGO_DATABASE*` (`core/config.py:24-25`). Do NOT remove `APPROVAL_FRONTEND_URL`/`APPROVAL_BASE_URL` — approval emails prefer the SPA URL and log a warning when unset (`core/approval.py:80-90`). The Azure `clientId/clientSecret/tenantId/userId` reads are mandatory today; this plan should convert them to optional (`config_env.get(...)`) since they are otherwise unused.

Frontend `.env.example`:

```dotenv
NEXT_PUBLIC_HOSTNAME=http://localhost:8000/api/v2
```

Remove `NEXT_PUBLIC_PARENT_APP_URL` (standalone).

---

## 7. Execution order, risks, open questions

### Order
1. Backend schema: add `User`/`Organization` models, repoint FKs, delete legacy + `s3_org` (`db/models.py`); set `DB_SCHEMA=explorer`.
2. Alembic baseline `0001_initial` + `env.py` schema handling; `scripts/create_admin.py`.
3. Rewrite `core/auth.py` (`X-User-Id`), `core/user_access.py`, `core/permissions.py` (drop fallback).
4. Update endpoints: `users.py` (CRUD+roles), `admin.py` (orgs), `groups.py`, `browse.py`, then the rest to new `get_current_user`. Remove the unauthenticated `/services/v2/*` routes and the UAM/legacy-coupled `/uam/folders` + `s3_explorer` fallback ONLY after the 2.6 step-3 legacy transformation is done (production) — immediately in greenfield.
5. Update tests + fixtures.
6. Frontend: identity source + `X-User-Id` clients, remove postMessage/legacy paths, dev user selector, admin/org/user UI, branding.
7. Datapoem/rhymedatapoem sweep + grep verification.
8. `.env.example` (both) + README updates.
9. Production only: run the 2.6 cutover backfill (orgs -> users -> legacy transform -> repoint) in a maintenance window, then clear the 7c go/no-go gates before flipping `DB_SCHEMA` and removing legacy paths.

### Risks
- Wide blast radius: JWT is wired through admin/browse/approval/otp/unonboard, not just `core/auth.py`.
- Dropping legacy `s3_explorer` fallback can hide folders for users relying on legacy access. In production this is only safe AFTER the mandatory legacy-access transformation in 2.6 step 3 (convert legacy rows into owned groups/grants); greenfield has no such data.
- Do NOT accidentally remove the authenticated `/services/*` routes — they are the only upload/delete/download/trash backend; there is no `/files/*` equivalent for those.
- Merging `s3_org` into `organizations` can silently drop `max_upload_size_bytes` (per-org upload cap) and `onboarded_by` (OTP approver) — both are used at runtime.
- Renaming settings (`BUCKET`, `SMTP_USERNAME`) in `.env` without refactoring `core/config.py` breaks boot; Azure vars crash import if unset.
- Header-based identity is impersonatable; keep behind `DEV_AUTH_MODE` and internal network only.
- Schema rename must not disturb S3 key/prefix layout (S3 paths use bucket/org names, not schema — low risk, verify).
- Production cutover must preserve existing integer user ids (bare-int FKs) or grants/memberships orphan.

### 7b. Testing / regression coverage (blast radius is large — ~19 test modules)

- Rework `tests/conftest.py` to seed owned `users`/`organizations` and override auth via `X-User-Id` instead of UAM fixtures + `rhymedatapoem` attach.
- Required regression suites: auth/`require_role` gating; org-admin vs global-admin scoping; user CRUD + role assignment; group membership/grant enforcement (`test_grant_enforcement.py`); upload/delete via `/services/*` (allowlist + size cap `test_upload_allowlist.py`); browse/trash; file rename/copy/move (`test_file_ops.py`); viewer; notifications; OTP + approval email flows (`test_otp.py`, `test_approval.py`); unonboard (`test_unonboard.py`); onboarding (`test_phase1_onboarding_auth.py`); cleanup cron (`test_cleanup_cron.py`).
- Add a smoke test that a fresh empty DB + `0001_initial` + bootstrap admin can create a user, onboard an org, and grant folder access end-to-end.

### 7c. Production cutover: go/no-go verification and rollback

Applies only if a production cutover is in scope (open question 7). Run all of this inside the maintenance window, against a copy first (staging clone of prod DB), then prod.

- Pre-cutover snapshot (for reconciliation + rollback):
  - Snapshot/export the source `s3_*` tables and the relevant UAM `user_data`/`subscriber` rows.
  - Persist a per-user access baseline: for every user, the set of `(org_id, prefix, access_level)` currently reachable via grants and via the legacy `s3_explorer` fallback. This is the ground truth the post-cutover state is compared against.
- Go/no-go gates (ALL must pass before flipping `DB_SCHEMA` and removing UAM/legacy paths):
  1. Referential integrity: every `user_id`/`created_by`/`onboarded_by`/`org_id` in owned `s3_*` tables resolves to an owned `users`/`organizations` row (zero orphans).
  2. Id preservation: owned `users.id` and `organizations.id` match the ids referenced by pre-existing rows (no re-id).
  3. User completeness: owned `users` count >= the day-one admin-list population from 2.6 step 2 (referenced ∪ onboarded-org members); spot-check pickers return expected members.
  4. Access parity: for every user, post-cutover reachable `(org_id, prefix, access_level)` is EQUAL or a SUPERSET of the pre-cutover baseline. Any regression must be an explicitly approved, listed exception.
  5. Singletons/config: `s3_platform_settings` row 1 present; per-org `max_upload_size_bytes` carried over; `onboarded_by` populated for OTP approver resolution.
  6. Smoke: browse, upload (`/services/*` + size cap), download, trash, group/grant enforcement, OTP + approval email, unonboard all pass against migrated data.
- Rollback: if any gate fails, do NOT flip `DB_SCHEMA` and do NOT remove the `s3_explorer` fallback / `/uam/folders`. Restore the pre-cutover snapshot, keep the app pointed at the original schema, and re-run after fixing the backfill. Because legacy removal is sequenced AFTER verification (2.6 sequencing + order step 9), rollback is a config revert, not a code revert.
- Post-cutover: retain the snapshot and access baseline for a defined window (e.g. 30 days) before dropping legacy tables permanently.

### Open questions to confirm
1. Delete the old `migrations/*.sql` files or archive them?
2. Include role `5 = AGENCY_HEAD` (only in `PLAN.md`) or keep the 4-role set?
3. Are any external systems currently calling the unauthenticated `/services/v2/*` routes (affects whether we can drop them immediately)?
4. Standalone `basePath` — keep `/explorer` or serve at root?
5. Org column naming: keep existing `org_name`/`is_active`/`subscription_id` on `organizations` (minimal refactor) or rename to `name`/`active`/`org_key` (cleaner, wide refactor)?
6. Is this greenfield-only, or is a production data cutover from the shared UAM DB also in scope? If cutover is in scope, the 2.6 user-migration scope (referenced-only vs all onboarded-org members) and the legacy `s3_explorer` transformation (step 3) become mandatory build items rather than a follow-on phase.
7. Rename `BUCKET`/`SMTP_USERNAME` env vars to friendlier names (requires `core/config.py` refactor) or keep as-is?