"use client";

import { useMemo, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "react-query";
import { ArrowRight, HardDrive, Users, Clock3, FileText } from "lucide-react";
import TopBar from "@/components/TopBar";
import EmptyState from "@/components/EmptyState";
import { listAccessibleOrgs } from "@/services/browse";
import { getOrganizations } from "@/services/admin";
import { getSelectedUserId } from "@/services/auth";
import { ApplicationContext } from "@/services/ContextProvider";
import { getOrgStats, setOrgStats, getRecentFiles } from "@/services/localStorage";

function getTimeOfDay() {
  const hour = new Date().getHours();
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}

export default function LandingPage() {
  const router = useRouter();
  const selectedUserId = getSelectedUserId() || 1;
  const { username, isAdmin } = useContext(ApplicationContext);
  const [orgStats, setOrgStatsLocal] = useState({});
  const [recentFiles, setRecentFiles] = useState([]);

  const { data: orgsData, isLoading } = useQuery(
    ["landing-orgs", selectedUserId],
    async () => {
      try {
        const accessible = await listAccessibleOrgs();
        if (Array.isArray(accessible) && accessible.length) return accessible;
      } catch {}
      if (isAdmin) {
        try {
          const adminOrgs = await getOrganizations();
          return Array.isArray(adminOrgs) ? adminOrgs : [];
        } catch {}
      }
      return [];
    },
    { retry: false, staleTime: 60_000 }
  );

  // Load org stats from localStorage on mount
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

  // Load recent files from localStorage
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

  const greetingName = username || orgsData?.[0]?.user_name || orgsData?.[0]?.username || "there";
  const user = { name: greetingName, email: "", avatarUrl: "" };

  // Admin-only metric: total orgs count
  const adminMetrics = isAdmin ? [
    { label: "Organizations", value: orgs.length, icon: Users },
    { label: "Total storage quota", value: formatBytes(orgs.reduce((s, o) => s + o.maxBytes, 0)), icon: HardDrive },
  ] : null;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopBar user={user} onSearch={() => {}} hideSearch={!isAdmin} />

      <main className="mx-auto max-w-6xl px-4 pb-12 pt-8 sm:px-6 lg:px-8">
        <section className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">
            Good {getTimeOfDay()}, {greetingName}
          </h1>
          <p className="text-sm text-muted-foreground">
            {isAdmin
              ? "Here\u2019s what\u2019s happening across your organizations."
              : "Welcome back. Select an organization to continue."}
          </p>
        </section>

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

        {!isAdmin && recentFiles.length > 0 && (
          <section className="mt-10">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              Recent files
            </h2>
            <div className="overflow-hidden rounded-xl border border-border bg-card">
              {recentFiles.map((item, idx) => (
                <button
                  key={`${item.key}-${idx}`}
                  type="button"
                  onClick={() => {
                    // Navigate to org/folder - simplified for now
                    console.log("Navigate to:", item);
                  }}
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

        <section className="mt-10">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            Your organizations
          </h2>

          {orgs.length === 0 && !isLoading ? (
            <EmptyState
              title="No organizations yet"
              body={isAdmin ? "Create or join one to start organizing your files." : "You have not been added to any organization yet. Contact your administrator."}
              actionLabel={isAdmin ? "Go to Admin Panel" : undefined}
              onAction={isAdmin ? () => router.push("/admin") : undefined}
            />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {orgs.map((org) => (
                <button
                  key={org.id}
                  type="button"
                  onClick={() => router.push(`/org/${org.id}`)}
                  className="flex w-full items-center justify-between rounded-xl border border-border bg-card p-4 text-left shadow-sm transition hover:border-accent hover:shadow-md"
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
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                </button>
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
