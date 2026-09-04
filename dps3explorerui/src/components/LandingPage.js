"use client";

import { useMemo, useContext, useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueries } from "react-query";
import {
  ArrowRight, ChevronDown, ChevronRight,
  HardDrive, Users, Clock3, FileText, Folder, Settings,
  Bell, ShieldAlert, Activity,
} from "lucide-react";
import TopBar from "@/components/TopBar";
import EmptyState from "@/components/EmptyState";
import StorageMeter from "@/components/StorageMeter";
import { listAccessibleOrgs, browseFolders, getOrgStorage } from "@/services/browse";
import { getOrganizations, getAdminMe, getAdminUserStats, getAuditEvents } from "@/services/admin";
import { getSelectedUserId } from "@/services/auth";
import { getExplorerAccess } from "@/services/access";
import { ApplicationContext } from "@/services/ContextProvider";
import { getRecentFiles } from "@/services/localStorage";
import { getNotifications } from "@/services/notifications";

function getTimeOfDay() {
  const hour = new Date().getHours();
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}

// Folder list lazy-loaded when an org card is expanded
function OrgFolders({ orgId, router }) {
  const { data, isLoading } = useQuery(
    ["landing-folders", orgId],
    () => browseFolders(orgId, ""),
    { staleTime: 60_000, retry: false }
  );

  if (isLoading) {
    return <p className="px-4 py-2 text-xs text-muted-foreground">Loading folders…</p>;
  }

  const folders = data?.folders ?? [];
  if (folders.length === 0) {
    return <p className="px-4 py-2 text-xs text-muted-foreground">No folders found.</p>;
  }

  return (
    <div className="border-t border-border divide-y divide-border">
      {folders.map((f) => (
        <button
          key={f.key}
          type="button"
          onClick={() => router.push(`/org/${orgId}?path=${encodeURIComponent(f.key)}`)}
          className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-gray-50 transition"
        >
          <Folder className="h-4 w-4 shrink-0 text-status-warning" strokeWidth={1.5} />
          <span className="truncate text-sm text-foreground">{f.name}</span>
          <ArrowRight className="ml-auto h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        </button>
      ))}
    </div>
  );
}

// Expandable org card — folders lazy-load on expand
function OrgCard({ org, router, isAdmin }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between p-4 text-left transition hover:border-accent"
      >
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-subtle text-sm font-semibold text-accent">
            {org.initials}
          </div>
          <div className="min-w-0">
            <p className="truncate text-base font-medium text-foreground">{org.name}</p>
            <p className="truncate text-sm text-muted-foreground capitalize">
              {org.role || "Member"}{isAdmin ? ` · ${org.members} members` : ""} · {org.fileCount} files
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); router.push(`/org/${org.id}`); }}
            className="rounded-md border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-gray-100 transition"
          >
            Open
          </button>
          {expanded
            ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
            : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
        </div>
      </button>

      {/* Storage meter visible to all users */}
      {org.totalBytes > 0 && (
        <div className="px-4 pb-3 pt-1 border-t border-border">
          <StorageMeter usedBytes={org.usedBytes} totalBytes={org.totalBytes} />
        </div>
      )}

      {expanded && <OrgFolders orgId={org.id} router={router} />}
    </div>
  );
}

export default function LandingPage() {
  const router = useRouter();
  const selectedUserId = getSelectedUserId();
  const { username: ctxUsername, isAdmin: ctxIsAdmin, setUsername, setIsAdmin } = useContext(ApplicationContext);
  const [recentFiles, setRecentFiles] = useState([]);
  const openNotifRef = useRef(null);

  // Run auth queries directly so the landing page is fully populated on first
  // load, without depending on the explorer layout having run first.
  const { data: access } = useQuery(
    ["explorer-access", selectedUserId],
    getExplorerAccess,
    { enabled: Boolean(selectedUserId), retry: false, staleTime: 60 * 1000 }
  );

  // getAdminMe returns 403 for non-admins — onError keeps adminMe undefined, treated as not-admin
  const { data: adminMe } = useQuery(
    ["admin-me", selectedUserId],
    getAdminMe,
    { enabled: Boolean(selectedUserId) && access?.can_access === true, retry: false, staleTime: 5 * 60 * 1000, onError: () => {} }
  );

  // Once access resolves, if adminMe is still undefined it means 403 → not admin
  // Never fall back to stale ctxIsAdmin once we have a fresh access response
  const resolvedIsAdmin = adminMe
    ? Boolean(adminMe.is_global_admin || adminMe.role_label === "admin" || adminMe.is_admin)
    : access
      ? false
      : ctxIsAdmin;
  const resolvedUsername = adminMe?.user_name || access?.user_name || ctxUsername;

  useEffect(() => {
    if (adminMe?.user_name) setUsername(adminMe.user_name);
    else if (access?.user_name) setUsername(access.user_name);
  }, [adminMe, access]);

  useEffect(() => {
    if (access) setIsAdmin(resolvedIsAdmin);
  }, [resolvedIsAdmin, access]);

  // Notifications for normal users
  const { data: notifData } = useQuery(
    ["notifications", selectedUserId],
    getNotifications,
    { enabled: Boolean(selectedUserId) && access?.can_access === true, staleTime: 60_000, retry: false, onError: () => {} }
  );
  const unreadCount = notifData?.unread_count ?? 0;
  const notifItems = (notifData?.items ?? []).slice(0, 4);

  // Today's audit events for admins
  const todayStr = new Date().toISOString().split("T")[0];
  const { data: auditData } = useQuery(
    ["landing-audit", selectedUserId],
    () => getAuditEvents({ dateFrom: todayStr, dateTo: todayStr, pageSize: 5 }),
    { enabled: Boolean(selectedUserId) && resolvedIsAdmin, staleTime: 60_000, retry: false, onError: () => {} }
  );
  const recentAuditEvents = auditData?.events ?? [];

  const { data: orgsData, isLoading } = useQuery(
    ["landing-orgs", selectedUserId],
    async () => {
      try {
        const accessible = await listAccessibleOrgs();
        if (Array.isArray(accessible) && accessible.length) return accessible;
      } catch {}
      if (resolvedIsAdmin) {
        try {
          const adminOrgs = await getOrganizations();
          return Array.isArray(adminOrgs) ? adminOrgs : [];
        } catch {}
      }
      return [];
    },
    { retry: false, staleTime: 60_000, enabled: Boolean(selectedUserId) && access?.can_access === true }
  );

  useEffect(() => {
    setRecentFiles(getRecentFiles());
  }, []);

  // Fetch storage + member counts per org in parallel once org list is known
  const orgIds = useMemo(() => (Array.isArray(orgsData) ? orgsData.map((o) => o.org_id ?? o.id) : []), [orgsData]);

  const storageResults = useQueries(
    orgIds.map((id) => ({
      queryKey: ["org-storage", id],
      queryFn: () => getOrgStorage(id),
      staleTime: 60_000,
      retry: false,
    }))
  );

  const memberResults = useQueries(
    orgIds.map((id) => ({
      queryKey: ["org-member-stats", id],
      queryFn: () => getAdminUserStats(id),
      staleTime: 60_000,
      retry: false,
      enabled: resolvedIsAdmin,
    }))
  );

  const orgs = useMemo(() => {
    if (!Array.isArray(orgsData)) return [];
    return orgsData.map((org, idx) => {
      const storage = storageResults[idx]?.data;
      const memberStats = memberResults[idx]?.data;
      return {
        id: org.org_id ?? org.id,
        name: org.org_name || org.folder_name || org.name || "Organization",
        role: org.role || org.role_label || "Member",
        usedBytes: storage?.used_bytes ?? 0,
        totalBytes: storage?.total_bytes ?? org.max_upload_size_bytes ?? 0,
        fileCount: storage?.file_count ?? 0,
        members: memberStats?.total_users ?? 0,
        initials: (org.org_name || org.folder_name || org.name || "Org")
          .split(/\s+/).slice(0, 2)
          .map((p) => p[0]?.toUpperCase() || "").join("") || "OR",
      };
    });
  }, [orgsData, storageResults, memberResults]);

  const greetingName = resolvedUsername || orgsData?.[0]?.user_name || orgsData?.[0]?.username || "there";
  const user = { name: greetingName, email: "", avatarUrl: "" };

  const totalUsers = memberResults.reduce((sum, r) => sum + (r.data?.total_users ?? 0), 0);

  const adminMetrics = resolvedIsAdmin ? [
    { label: "Organizations", value: orgs.length, icon: Users },
    { label: "Total Users", value: totalUsers, icon: Activity },
    { label: "Total storage quota", value: formatBytes(orgs.reduce((s, o) => s + o.totalBytes, 0)), icon: HardDrive },
  ] : null;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopBar user={user} onSearch={() => {}} hideSearch={!resolvedIsAdmin} onOpenNotifications={openNotifRef} />

      <main className="mx-auto max-w-6xl px-4 pb-12 pt-8 sm:px-6 lg:px-8">
        {/* Greeting */}
        <section className="flex items-start justify-between">
          <div className="space-y-1">
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">
              Good {getTimeOfDay()}, {greetingName}
            </h1>
            <p className="text-sm text-muted-foreground">
              {resolvedIsAdmin
                ? "Here\u2019s what\u2019s happening across your organizations."
                : "Welcome back. Select an organization to continue."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {resolvedIsAdmin && (
              <button
                type="button"
                onClick={() => router.push("/admin")}
                className="flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground shadow-sm hover:bg-gray-50 transition"
              >
                <Settings className="h-4 w-4" strokeWidth={1.5} />
                Admin Panel
              </button>
            )}
          </div>
        </section>

        {/* Admin metrics */}
        {adminMetrics && (
          <section className="mt-6 grid gap-4 md:grid-cols-3">
            {adminMetrics.map(({ label, value, icon: Icon }) => (
              <div key={label} className="rounded-xl border border-border bg-card p-5 shadow-sm">
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                  <span>{label}</span>
                  <Icon className="h-4 w-4" />
                </div>
                <div className="mt-4 text-3xl font-semibold text-foreground">{value}</div>
              </div>
            ))}
          </section>
        )}

        {/* Notifications section — normal users only */}
        {!resolvedIsAdmin && (
          <section className="mt-6">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Bell className="h-4 w-4 text-muted-foreground" />
                <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  Notifications {unreadCount > 0 && <span className="ml-1 inline-flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-bold min-w-[18px] h-[18px] px-1">{unreadCount > 99 ? "99+" : unreadCount}</span>}
                </h2>
              </div>
              {notifItems.length > 0 && (
                <button
                  type="button"
                  onClick={() => openNotifRef.current?.()}
                  className="text-xs text-muted-foreground hover:text-foreground transition"
                >
                  See all →
                </button>
              )}
            </div>
            <div className="overflow-hidden rounded-xl border border-border bg-card divide-y divide-border">
              {notifItems.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-center">
                  <Bell className="h-8 w-8 text-muted-foreground/40 mb-2" strokeWidth={1.5} />
                  <p className="text-sm text-muted-foreground">You&apos;re all caught up!</p>
                  <p className="text-xs text-muted-foreground/70 mt-1">No notifications yet.</p>
                </div>
              ) : (
                notifItems.map((n) => (
                  <button
                    key={n.id}
                    type="button"
                    onClick={() => openNotifRef.current?.()}
                    className={`flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-gray-50 transition ${!n.is_read ? "bg-blue-50/40" : ""}`}
                  >
                    <Bell className={`h-4 w-4 mt-0.5 shrink-0 ${!n.is_read ? "text-blue-500" : "text-muted-foreground"}`} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-foreground truncate">{n.title}</p>
                      <p className="text-xs text-muted-foreground line-clamp-1">{n.message}</p>
                    </div>
                    <span className="text-xs text-muted-foreground whitespace-nowrap">{formatTimeAgo(new Date(n.created_at).getTime())}</span>
                  </button>
                ))
              )}
            </div>
          </section>
        )}

        {/* Recent audit activity — admins only */}
        {resolvedIsAdmin && recentAuditEvents.length > 0 && (
          <section className="mt-6">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-muted-foreground" />
                <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-muted-foreground">Today&apos;s Activity</h2>
              </div>
              <button
                type="button"
                onClick={() => router.push("/admin/audit")}
                className="text-xs text-muted-foreground hover:text-foreground transition"
              >
                View full audit log →
              </button>
            </div>
            <div className="overflow-hidden rounded-xl border border-border bg-card divide-y divide-border">
              {recentAuditEvents.map((ev) => (
                <div key={ev.event_id} className="flex items-center gap-3 px-4 py-3">
                  <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border bg-gray-50 text-gray-600 border-gray-200 whitespace-nowrap">
                    {ev.event_label || ev.event_type}
                  </span>
                  <span className="text-sm text-foreground truncate flex-1">{ev.display_target || ev.target_key || "—"}</span>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">{ev.user_name || ev.user_id}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Recent files — only for entries that have a saved orgId */}
        {recentFiles.filter((f) => f.orgId).length > 0 && (
          <section className="mt-10">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              Recent files
            </h2>
            <div className="overflow-hidden rounded-xl border border-border bg-card">
              {recentFiles.filter((f) => f.orgId).map((item, idx) => (
                <button
                  key={`${item.key}-${idx}`}
                  type="button"
                  onClick={() =>
                    router.push(
                      `/org/${item.orgId}${item.path ? `?path=${encodeURIComponent(item.path)}` : ""}`
                    )
                  }
                  className="flex w-full items-center gap-3 border-b border-border px-4 py-3 text-left last:border-b-0 transition hover:bg-gray-50"
                >
                  <div className="flex h-9 w-9 items-center justify-center rounded-md bg-muted text-muted-foreground">
                    <FileText className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-foreground">{item.name}</p>
                  </div>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Clock3 className="h-3.5 w-3.5" />
                    <span className="whitespace-nowrap">{formatTimeAgo(item.timestamp)}</span>
                  </div>
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Org cards with lazy-loaded folders */}
        <section className="mt-10">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            Your organizations
          </h2>

          {orgs.length === 0 && !isLoading ? (
            <EmptyState
              title="No organizations yet"
              body={resolvedIsAdmin
                ? "Create or join one to start organizing your files."
                : "You have not been added to any organization yet. Contact your administrator."}
              actionLabel={resolvedIsAdmin ? "Go to Admin Panel" : undefined}
              onAction={resolvedIsAdmin ? () => router.push("/admin") : undefined}
            />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {orgs.map((org) => (
                <OrgCard key={org.id} org={org} router={router} isAdmin={resolvedIsAdmin} />
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`;
}

function formatTimeAgo(timestamp) {
  if (!timestamp) return "";
  const diff = Date.now() - timestamp;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
