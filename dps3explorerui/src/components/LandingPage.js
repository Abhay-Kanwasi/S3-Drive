"use client";

import { useMemo, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "react-query";
import {
  ArrowRight, ChevronDown, ChevronRight,
  HardDrive, Users, Clock3, FileText, Folder, Settings,
} from "lucide-react";
import TopBar from "@/components/TopBar";
import EmptyState from "@/components/EmptyState";
import { listAccessibleOrgs, browseFolders } from "@/services/browse";
import { getOrganizations, getAdminMe } from "@/services/admin";
import { getSelectedUserId } from "@/services/auth";
import { getExplorerAccess } from "@/services/access";
import { ApplicationContext } from "@/services/ContextProvider";
import { getOrgStats, getRecentFiles } from "@/services/localStorage";

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
function OrgCard({ org, router }) {
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
              {org.role || "Member"} · {org.members} members · {org.fileCount} files
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

      {expanded && <OrgFolders orgId={org.id} router={router} />}
    </div>
  );
}

export default function LandingPage() {
  const router = useRouter();
  const selectedUserId = getSelectedUserId();
  const { username: ctxUsername, isAdmin: ctxIsAdmin, setUsername, setIsAdmin } = useContext(ApplicationContext);
  const [orgStats, setOrgStatsLocal] = useState({});
  const [recentFiles, setRecentFiles] = useState([]);

  // Run auth queries directly so the landing page is fully populated on first
  // load, without depending on the explorer layout having run first.
  const { data: access } = useQuery(
    ["explorer-access", selectedUserId],
    getExplorerAccess,
    { enabled: Boolean(selectedUserId), retry: false, staleTime: 60 * 1000 }
  );

  const { data: adminMe } = useQuery(
    ["admin-me", selectedUserId],
    getAdminMe,
    { enabled: Boolean(selectedUserId) && access?.can_access === true, retry: false, staleTime: 5 * 60 * 1000 }
  );

  // Sync resolved identity into context so other parts of the app benefit too
  useEffect(() => {
    if (adminMe?.user_name) setUsername(adminMe.user_name);
    else if (access?.user_name) setUsername(access.user_name);
  }, [adminMe, access]);

  useEffect(() => {
    if (adminMe) {
      setIsAdmin(Boolean(adminMe.is_global_admin || adminMe.role_label === "admin" || adminMe.is_admin));
    }
  }, [adminMe]);

  // Use locally resolved values; fall back to context if queries haven't settled yet
  const resolvedIsAdmin = adminMe
    ? Boolean(adminMe.is_global_admin || adminMe.role_label === "admin" || adminMe.is_admin)
    : ctxIsAdmin;
  const resolvedUsername = adminMe?.user_name || access?.user_name || ctxUsername;

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
    { retry: false, staleTime: 60_000, enabled: Boolean(selectedUserId) }
  );

  useEffect(() => {
    if (Array.isArray(orgsData)) {
      const stats = {};
      orgsData.forEach((org) => {
        const stored = getOrgStats(org.org_id ?? org.id);
        stats[org.org_id ?? org.id] = stored || { fileCount: 0, members: 0 };
      });
      setOrgStatsLocal(stats);
    }
  }, [orgsData]);

  useEffect(() => {
    setRecentFiles(getRecentFiles());
  }, []);

  const orgs = useMemo(() => {
    if (!Array.isArray(orgsData)) return [];
    return orgsData.map((org) => ({
      id: org.org_id ?? org.id,
      name: org.org_name || org.folder_name || org.name || "Organization",
      role: org.role || org.role_label || "Member",
      maxBytes: org.max_upload_size_bytes || 0,
      fileCount: (orgStats[org.org_id ?? org.id]?.fileCount ?? 0) || 0,
      members: (orgStats[org.org_id ?? org.id]?.members ?? 0) || 0,
      initials: (org.org_name || org.folder_name || org.name || "Org")
        .split(/\s+/).slice(0, 2)
        .map((p) => p[0]?.toUpperCase() || "").join("") || "OR",
    }));
  }, [orgsData, orgStats]);

  const greetingName = resolvedUsername || orgsData?.[0]?.user_name || orgsData?.[0]?.username || "there";
  const user = { name: greetingName, email: "", avatarUrl: "" };

  const adminMetrics = resolvedIsAdmin ? [
    { label: "Organizations", value: orgs.length, icon: Users },
    { label: "Total storage quota", value: formatBytes(orgs.reduce((s, o) => s + o.maxBytes, 0)), icon: HardDrive },
  ] : null;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopBar user={user} onSearch={() => {}} hideSearch={!resolvedIsAdmin} />

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
        </section>

        {/* Admin metrics */}
        {adminMetrics && (
          <section className="mt-6 grid gap-4 md:grid-cols-2">
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
                <OrgCard key={org.id} org={org} router={router} />
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
