"use client";
import { useContext, useState, useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useQuery } from "react-query";
import { Database, Users, UserCircle, FileText, Loader2, ShieldX, Settings } from "lucide-react";
import { ApplicationContext } from "@/services/ContextProvider";
import { getExplorerAccess, isS3ExplorerDeactivated } from "@/services/access";
import S3ExplorerAccessBlocked from "@/components/S3ExplorerAccessBlocked";
import { AdminProvider, useAdminMe } from "./AdminContext";

// Approval review/confirm renders without admin gating (handles its own auth UX).
const APPROVAL_ROUTE = "/admin/approval";

const adminNavItems = [
  { label: "Buckets", href: "/admin", icon: Database },
  { label: "User Groups", href: "/admin/groups", icon: Users },
  { label: "Users", href: "/admin/users", icon: UserCircle },
];

const auditNavItems = [
  { label: "Audit Log", href: "/admin/audit", icon: FileText },
];

const settingsNavItems = [
  { label: "Platform Settings", href: "/admin/settings", icon: Settings },
];

export default function AdminLayout({ children }) {
  const pathname = usePathname();
  if (pathname === APPROVAL_ROUTE) {
    return (
      <AdminProvider>
        <AdminLayoutInner skipAccessCheck>{children}</AdminLayoutInner>
      </AdminProvider>
    );
  }
  return (
    <AdminProvider>
      <AdminLayoutInner>{children}</AdminLayoutInner>
    </AdminProvider>
  );
}

function AdminLayoutInner({ children, skipAccessCheck = false }) {
  const router = useRouter();
  const pathname = usePathname();
  const { username, isAdmin, authToken } = useContext(ApplicationContext);
  const { me, isLoading, isError, error } = useAdminMe();
  const [mounted, setMounted] = useState(false);

  const { data: access, isLoading: accessLoading } = useQuery(
    "explorer-access",
    getExplorerAccess,
    { enabled: mounted, retry: false, staleTime: 60 * 1000 },
  );

  useEffect(() => {
    setMounted(true);
  }, []);

  const errMsg = (error?.message || "").toLowerCase();
  const s3DeactivatedFromMe =
    errMsg.includes("s3 explorer") || errMsg.includes("deactivated in s3");
  const s3Deactivated =
    (access && isS3ExplorerDeactivated(access)) || s3DeactivatedFromMe;

  if (!mounted) {
    return <div className="h-full w-full bg-background" aria-hidden="true" />;
  }

  if (!skipAccessCheck) {
    if (accessLoading) {
      return <div className="h-full w-full bg-background" aria-hidden="true" />;
    }
    if (access && !access.can_access) {
      return <S3ExplorerAccessBlocked access={access} />;
    }

    if (isLoading) {
      return (
        <div className="flex items-center justify-center h-full w-full">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      );
    }

    if (s3Deactivated) {
      return (
        <div className="flex flex-col items-center justify-center h-full w-full gap-3 px-6">
          <ShieldX className="w-10 h-10 text-amber-600" strokeWidth={1} />
          <p className="text-foreground font-medium">S3 Explorer access deactivated</p>
          <p className="text-sm text-muted-foreground max-w-md text-center">
            Your S3 Explorer access has been deactivated. You cannot use the admin
            panel or explorer until an administrator restores your access. Please
            contact your organization administrator.
          </p>
          <button
            onClick={() => router.push("/")}
            className="mt-2 px-4 py-2 bg-new-button-bg rounded-lg text-sm font-semibold text-foreground hover-button"
          >
            Back to home
          </button>
        </div>
      );
    }

    if (isError || (!isAdmin && !me)) {
      return (
        <div className="flex flex-col items-center justify-center h-full w-full gap-3">
          <ShieldX className="w-10 h-10 text-muted-foreground" strokeWidth={1} />
          <p className="text-foreground font-medium">Access Denied</p>
          <p className="text-sm text-muted-foreground max-w-sm text-center">
            You do not have permission to access the admin panel.
          </p>
          <button
            onClick={() => router.push("/")}
            className="mt-2 px-4 py-2 bg-new-button-bg rounded-lg text-sm font-semibold text-foreground hover-button"
          >
            Back to Explorer
          </button>
        </div>
      );
    }
  }

  const roleLabel = me?.role_label || "";
  const isGlobalAdmin = me?.is_global_admin;

  const visibleNavItems = isGlobalAdmin
    ? adminNavItems
    : adminNavItems.filter(item => item.href !== "/admin");

  return (
    <div className="flex h-full w-full overflow-hidden">
      <aside className="bg-white flex-shrink-0 w-52 h-full flex flex-col border-r border-border">
        <div className="flex-1 flex flex-col pt-6 overflow-y-auto">
          <p className="px-5 text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-2">
            Manage
          </p>
          <nav className="px-3 space-y-0.5">
            {visibleNavItems.map((item) => {
              const isActive = pathname === item.href ||
                (item.href !== "/admin" && pathname.startsWith(item.href));
              const Icon = item.icon;
              return (
                <button
                  key={item.href}
                  onClick={() => router.push(item.href)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] transition-colors ${
                    isActive
                      ? "bg-new-bg-light text-foreground font-medium"
                      : "text-muted-foreground hover:text-foreground hover:bg-accent"
                  }`}
                >
                  <Icon className="w-4 h-4 flex-shrink-0" strokeWidth={1.5} />
                  {item.label}
                </button>
              );
            })}
          </nav>

          <p className="px-5 text-[11px] font-medium text-muted-foreground uppercase tracking-wider mt-6 mb-2">
            Audit
          </p>
          <nav className="px-3 space-y-0.5">
            {auditNavItems.map((item) => {
              const isActive = pathname === item.href;
              const Icon = item.icon;
              return (
                <button
                  key={item.href}
                  onClick={() => router.push(item.href)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] transition-colors ${
                    isActive
                      ? "bg-new-bg-light text-foreground font-medium"
                      : "text-muted-foreground hover:text-foreground hover:bg-accent"
                  }`}
                >
                  <Icon className="w-4 h-4 flex-shrink-0" strokeWidth={1.5} />
                  {item.label}
                </button>
              );
            })}
          </nav>

          {isGlobalAdmin && (
            <>
              <p className="px-5 text-[11px] font-medium text-muted-foreground uppercase tracking-wider mt-6 mb-2">
                Configuration
              </p>
              <nav className="px-3 space-y-0.5">
                {settingsNavItems.map((item) => {
                  const isActive = pathname === item.href;
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.href}
                      onClick={() => router.push(item.href)}
                      className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] transition-colors ${
                        isActive
                          ? "bg-new-bg-light text-foreground font-medium"
                          : "text-muted-foreground hover:text-foreground hover:bg-accent"
                      }`}
                    >
                      <Icon className="w-4 h-4 flex-shrink-0" strokeWidth={1.5} />
                      {item.label}
                    </button>
                  );
                })}
              </nav>
            </>
          )}
        </div>

        <div className="flex-shrink-0 px-4 py-4 border-t border-border">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-full bg-new-bg flex items-center justify-center text-foreground text-xs font-semibold">
              {username ? username.charAt(0).toUpperCase() : "U"}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-foreground truncate">
                {username || "Admin"}
              </p>
              <p className="text-[10px] text-muted-foreground capitalize">
                {isGlobalAdmin ? roleLabel.replace("_", " ") : "Org Admin"}
              </p>
            </div>
          </div>
          <button
            onClick={() => router.push("/")}
            className="mt-2 w-full text-left text-[11px] text-muted-foreground hover:text-foreground transition-colors"
          >
            ← Back to Explorer
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto bg-background p-8">
        {children}
      </main>
    </div>
  );
}
