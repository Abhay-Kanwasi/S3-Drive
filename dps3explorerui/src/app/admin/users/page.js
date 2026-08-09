"use client";
import { useState, useCallback, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "react-query";
import {
  UserCircle,
  Search,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Building2,
  FolderKey,
  Users,
  Download,
  X,
  Shield,
  Plus,
  Pencil,
} from "lucide-react";
import { useAdminMe } from "../AdminContext";
import {
  getAdminUsers,
  getAdminUserDetail,
  getAdminUserStats,
  getOrganizations,
  exportUsersCSV,
  deactivateAdminUser,
  reactivateAdminUser,
  createAdminUser,
  updateAdminUser,
} from "@/services/admin";

const ROLE_BADGES = {
  super_admin: { label: "SUPER ADMIN", cls: "bg-gray-900 text-white" },
  master_admin: { label: "MASTER ADMIN", cls: "bg-gray-900 text-white" },
  admin: { label: "ORG ADMIN", cls: "bg-blue-50 text-blue-700 border border-blue-200" },
  user: { label: "END USER", cls: "bg-gray-100 text-gray-600 border border-gray-200" },
};

const ROLE_OPTIONS = [
  { value: "user", label: "End User" },
  { value: "admin", label: "Org Admin" },
  { value: "master_admin", label: "Master Admin" },
  { value: "super_admin", label: "Super Admin" },
];

const PAGE_SIZE = 50;

function isGlobalRole(roleLabel) {
  return roleLabel === "master_admin" || roleLabel === "super_admin";
}

/** Account-level active flag (compat: account_active or legacy uam_active). */
function isAccountActive(u) {
  if (!u) return true;
  if (u.account_active != null) return u.account_active !== false;
  if (u.uam_active != null) return u.uam_active !== false;
  return true;
}

/* ───────── Detail Panel ───────── */

function UserDetailPanel({ userId, onClose, onDeactivated, onEdit }) {
  const { me } = useAdminMe();
  const queryClient = useQueryClient();
  const [showDeactivate, setShowDeactivate] = useState(false);
  const [showReactivate, setShowReactivate] = useState(false);

  const { data: detail, isLoading } = useQuery(
    ["admin-user-detail", userId],
    () => getAdminUserDetail(userId),
    { enabled: !!userId },
  );

  const deactivateMutation = useMutation(
    () => deactivateAdminUser(userId),
    {
      onSuccess: () => {
        setShowDeactivate(false);
        queryClient.invalidateQueries(["admin-user-detail", userId]);
        queryClient.invalidateQueries(["admin-users"]);
        queryClient.invalidateQueries(["admin-user-stats"]);
        onDeactivated?.();
      },
    },
  );

  const reactivateMutation = useMutation(
    () => reactivateAdminUser(userId),
    {
      onSuccess: () => {
        setShowReactivate(false);
        queryClient.invalidateQueries(["admin-user-detail", userId]);
        queryClient.invalidateQueries(["admin-users"]);
        queryClient.invalidateQueries(["admin-user-stats"]);
      },
    },
  );

  if (!userId) return null;

  const b = detail ? ROLE_BADGES[detail.role_label] || ROLE_BADGES.user : null;
  const isMaster = detail && isGlobalRole(detail.role_label);
  const isOrg = detail?.role_label === "admin";
  const accountOk = isAccountActive(detail);
  const canDeactivate = Boolean(
    detail &&
      accountOk &&
      !detail.s3_deactivated &&
      detail.id !== me?.id &&
      !(detail.role_label === "super_admin" && me?.role_label !== "super_admin") &&
      !(
        !me?.is_global_admin &&
        (detail.role_label === "master_admin" || detail.role_label === "super_admin")
      ),
  );

  const canReactivate = Boolean(
    detail &&
      accountOk &&
      detail.s3_deactivated &&
      me?.is_global_admin &&
      !(detail.role_label === "super_admin" && me?.role_label !== "super_admin"),
  );

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />
      <div className="relative w-full max-w-sm bg-white border-l border-border shadow-xl flex flex-col animate-in slide-in-from-right-full duration-200">
        {/* Close */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 rounded hover:bg-accent text-muted-foreground"
        >
          <X className="w-4 h-4" />
        </button>

        {isLoading || !detail ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="px-6 pt-6 pb-5 border-b border-border">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-gray-800 flex items-center justify-center text-white text-lg font-semibold flex-shrink-0">
                  {(detail.user_name || detail.email || "?")
                    .charAt(0)
                    .toUpperCase()}
                </div>
                <div className="min-w-0">
                  <p className="text-base font-semibold text-foreground truncate">
                    {detail.user_name || "—"}
                  </p>
                  <p className="text-sm text-muted-foreground truncate">
                    {detail.email || "—"}
                  </p>
                </div>
              </div>
            </div>

            {/* Fields */}
            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
              <DetailField label="Organization">
                <span className="text-sm text-foreground">
                  {isMaster ? "—" : detail.org_name || "—"}
                </span>
              </DetailField>

              <DetailField label="Role">
                <span
                  className={`inline-block text-[11px] font-semibold px-2.5 py-0.5 rounded-full whitespace-nowrap ${b.cls}`}
                >
                  {b.label}
                </span>
              </DetailField>

              <DetailField label="Status">
                {detail.active ? (
                  <span className="inline-flex items-center gap-1.5 text-sm font-medium text-green-700">
                    <span className="w-2 h-2 rounded-full bg-green-500" />
                    Active
                  </span>
                ) : !accountOk ? (
                  <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
                    <span className="w-2 h-2 rounded-full bg-gray-300" />
                    Inactive (account)
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 text-sm text-amber-700">
                    <span className="w-2 h-2 rounded-full bg-amber-500" />
                    Inactive (S3 Explorer)
                  </span>
                )}
              </DetailField>

              <DetailField label="Groups">
                {isMaster ? (
                  <span className="text-sm text-muted-foreground">—</span>
                ) : detail.groups.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {detail.groups.map((g) => (
                      <span
                        key={g.id}
                        className="inline-flex items-center gap-1 text-xs font-medium bg-new-bg rounded-full px-2.5 py-1 text-foreground"
                      >
                        <Users className="w-3 h-3" strokeWidth={1.5} />
                        {g.name}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-sm text-muted-foreground">—</span>
                )}
              </DetailField>

              <DetailField label="Folder Access">
                {isMaster ? (
                  <span className="text-sm text-muted-foreground">—</span>
                ) : isOrg ? (
                  <span className="text-sm text-muted-foreground italic">
                    All org folders{" "}
                    <span className="font-semibold text-green-600 not-italic">
                      READ-WRITE
                    </span>
                  </span>
                ) : detail.folder_access.length > 0 ? (
                  <div className="space-y-2">
                    {detail.folder_access.map((fa, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between gap-2 text-sm"
                      >
                        <span className="font-mono text-muted-foreground truncate flex items-center gap-1.5">
                          <FolderKey className="w-3.5 h-3.5 flex-shrink-0" strokeWidth={1.5} />
                          {fa.prefix}
                        </span>
                        <span
                          className={`text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${
                            fa.access_level === "read_write"
                              ? "bg-green-50 text-green-700 border border-green-200"
                              : "bg-blue-50 text-blue-700 border border-blue-200"
                          }`}
                        >
                          {fa.access_level === "read_write"
                            ? "READ-WRITE"
                            : "READ"}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <span className="text-sm text-muted-foreground">—</span>
                )}
              </DetailField>

              <DetailField label="User ID">
                <span className="text-sm font-mono text-muted-foreground">
                  usr_{detail.id}
                </span>
              </DetailField>
            </div>

            {/* Footer actions */}
            <div className="px-6 py-4 border-t border-border space-y-2">
              {me?.is_global_admin && (
                <button
                  type="button"
                  onClick={() => onEdit?.(detail)}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 border border-border rounded-lg text-sm font-medium text-foreground bg-white hover:bg-accent transition-colors"
                >
                  <Pencil className="w-3.5 h-3.5" strokeWidth={1.5} />
                  Edit Role
                </button>
              )}
              <div className="flex items-center gap-3">
                <button
                  disabled
                  title="Audit log coming soon"
                  className="flex-1 flex items-center justify-center gap-2 px-3 py-2 border border-border rounded-lg text-sm font-medium text-muted-foreground bg-white cursor-not-allowed opacity-60"
                >
                  <Shield className="w-3.5 h-3.5" strokeWidth={1.5} />
                  View Audit Log
                </button>
                {accountOk && !detail.s3_deactivated ? (
                  <button
                    disabled={!canDeactivate}
                    title={
                      detail.id === me?.id
                        ? "You cannot deactivate your own account"
                        : !canDeactivate
                          ? "You cannot deactivate this user"
                          : "Deactivate S3 Explorer access"
                    }
                    onClick={() => setShowDeactivate(true)}
                    className="flex-1 flex items-center justify-center gap-2 px-3 py-2 border border-red-200 rounded-lg text-sm font-medium text-red-600 bg-white hover:bg-red-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-white"
                  >
                    Deactivate
                  </button>
                ) : (
                  <button
                    disabled={!canReactivate}
                    title={
                      !accountOk
                        ? "Account is inactive — reactivate the account first"
                        : !me?.is_global_admin
                          ? "Only master or super admins can reactivate S3 access"
                          : !canReactivate
                            ? "You cannot reactivate this user"
                            : "Restore S3 Explorer access (30-day grace)"
                    }
                    onClick={() => setShowReactivate(true)}
                    className="flex-1 flex items-center justify-center gap-2 px-3 py-2 border border-green-200 rounded-lg text-sm font-medium text-green-700 bg-white hover:bg-green-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-white"
                  >
                    Reactivate
                  </button>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {showDeactivate && detail && (
        <DeactivateConfirm
          userName={detail.user_name || detail.email || "this user"}
          loading={deactivateMutation.isLoading}
          error={deactivateMutation.error?.message}
          onConfirm={() => deactivateMutation.mutate()}
          onCancel={() => {
            setShowDeactivate(false);
            deactivateMutation.reset();
          }}
        />
      )}

      {showReactivate && detail && (
        <ReactivateConfirm
          userName={detail.user_name || detail.email || "this user"}
          loading={reactivateMutation.isLoading}
          error={reactivateMutation.error?.message}
          onConfirm={() => reactivateMutation.mutate()}
          onCancel={() => {
            setShowReactivate(false);
            reactivateMutation.reset();
          }}
        />
      )}
    </div>
  );
}

function ReactivateConfirm({ userName, loading, error, onConfirm, onCancel }) {
  return (
    <div className="fixed inset-0 bg-black/40 z-[60] flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
        <p className="text-[11px] font-semibold text-green-700 uppercase tracking-wide mb-2">
          Confirm · Reactivate
        </p>
        <h3 className="text-base font-semibold text-foreground mb-3">
          Reactivate {userName}?
        </h3>
        <p className="text-sm text-muted-foreground mb-4">
          This restores S3 Explorer access only. The account must still be
          active. Group memberships are kept if the nightly cleanup has not run.
          Allowed within 30 days of S3 deactivation (from the deactivation date).
        </p>
        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-green-700 text-white rounded-lg text-sm font-semibold hover:bg-green-800 disabled:opacity-50"
          >
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            Reactivate
          </button>
        </div>
      </div>
    </div>
  );
}

function DeactivateConfirm({ userName, loading, error, onConfirm, onCancel }) {
  return (
    <div className="fixed inset-0 bg-black/40 z-[60] flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
        <p className="text-[11px] font-semibold text-red-600 uppercase tracking-wide mb-2">
          Confirm · Deactivate
        </p>
        <h3 className="text-base font-semibold text-foreground mb-3">
          Deactivate {userName}?
        </h3>
        <p className="text-sm text-muted-foreground mb-2">
          This deactivates S3 Explorer access only (not the account):
        </p>
        <ul className="text-sm text-muted-foreground list-disc pl-5 space-y-1 mb-4">
          <li>Block S3 Explorer immediately on the next API call</li>
          <li>Account remains active for other purposes</li>
          <li>Group memberships removed after 30 days (nightly job)</li>
        </ul>
        {error && (
          <p className="text-sm text-red-600 mb-3">{error}</p>
        )}
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-destructive text-white rounded-lg text-sm font-semibold hover:bg-destructive/90 disabled:opacity-50"
          >
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            Deactivate
          </button>
        </div>
      </div>
    </div>
  );
}

function DetailField({ label, children }) {
  return (
    <div>
      <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide mb-1.5">
        {label}
      </p>
      {children}
    </div>
  );
}

/* ───────── Main Page ───────── */

function CreateUserModal({ orgs, onClose }) {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("user");
  const [organizationId, setOrganizationId] = useState("");
  const [error, setError] = useState("");

  const needsOrg = role === "user" || role === "admin";

  const mutation = useMutation(createAdminUser, {
    onSuccess: () => {
      queryClient.invalidateQueries(["admin-users"]);
      queryClient.invalidateQueries(["admin-user-stats"]);
      onClose();
    },
    onError: (err) => setError(err.message),
  });

  const handleSubmit = () => {
    setError("");
    if (!username.trim() || !email.trim()) {
      setError("Username and email are required");
      return;
    }
    if (needsOrg && !organizationId) {
      setError("Organization is required for this role");
      return;
    }
    mutation.mutate({
      username: username.trim(),
      email: email.trim(),
      role,
      organization_id: organizationId ? Number(organizationId) : null,
      active: true,
    });
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-foreground">Create User</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>
        <label className="block text-sm">
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Username</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mt-1 w-full px-3 py-2 border border-border rounded-lg text-sm outline-none"
            autoFocus
          />
        </label>
        <label className="block text-sm">
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full px-3 py-2 border border-border rounded-lg text-sm outline-none"
          />
        </label>
        <label className="block text-sm">
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Role</span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="mt-1 w-full px-3 py-2 border border-border rounded-lg text-sm bg-white"
          >
            {ROLE_OPTIONS.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </label>
        {needsOrg && (
          <label className="block text-sm">
            <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Organization</span>
            <select
              value={organizationId}
              onChange={(e) => setOrganizationId(e.target.value)}
              className="mt-1 w-full px-3 py-2 border border-border rounded-lg text-sm bg-white"
            >
              <option value="">Select organization…</option>
              {(orgs || []).map((o) => (
                <option key={o.id} value={o.id}>{o.org_name}</option>
              ))}
            </select>
          </label>
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={mutation.isLoading}
            className="flex items-center gap-2 px-4 py-2 bg-new-button-bg rounded-lg text-sm font-semibold disabled:opacity-50"
          >
            {mutation.isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
            Create
          </button>
        </div>
      </div>
    </div>
  );
}

function EditUserModal({ user, orgs, onClose }) {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState(user.user_name || user.username || "");
  const [email, setEmail] = useState(user.email || "");
  const [role, setRole] = useState(user.role_label || "user");
  const [organizationId, setOrganizationId] = useState(
    user.organization_id || user.org_id || "",
  );
  const [error, setError] = useState("");

  const needsOrg = role === "user" || role === "admin";

  const mutation = useMutation(
    (patch) => updateAdminUser(user.id, patch),
    {
      onSuccess: () => {
        queryClient.invalidateQueries(["admin-users"]);
        queryClient.invalidateQueries(["admin-user-detail", user.id]);
        queryClient.invalidateQueries(["admin-user-stats"]);
        onClose();
      },
      onError: (err) => setError(err.message),
    },
  );

  const handleSubmit = () => {
    setError("");
    if (!username.trim() || !email.trim()) {
      setError("Username and email are required");
      return;
    }
    if (needsOrg && !organizationId) {
      setError("Organization is required for this role");
      return;
    }
    mutation.mutate({
      username: username.trim(),
      email: email.trim(),
      role,
      organization_id: needsOrg ? Number(organizationId) : null,
    });
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-[60] flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-foreground">Edit User / Role</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>
        <label className="block text-sm">
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Username</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mt-1 w-full px-3 py-2 border border-border rounded-lg text-sm outline-none"
          />
        </label>
        <label className="block text-sm">
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full px-3 py-2 border border-border rounded-lg text-sm outline-none"
          />
        </label>
        <label className="block text-sm">
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Role</span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="mt-1 w-full px-3 py-2 border border-border rounded-lg text-sm bg-white"
          >
            {ROLE_OPTIONS.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </label>
        {needsOrg && (
          <label className="block text-sm">
            <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Organization</span>
            <select
              value={organizationId || ""}
              onChange={(e) => setOrganizationId(e.target.value)}
              className="mt-1 w-full px-3 py-2 border border-border rounded-lg text-sm bg-white"
            >
              <option value="">Select organization…</option>
              {(orgs || []).map((o) => (
                <option key={o.id} value={o.id}>{o.org_name}</option>
              ))}
            </select>
          </label>
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={mutation.isLoading}
            className="flex items-center gap-2 px-4 py-2 bg-new-button-bg rounded-lg text-sm font-semibold disabled:opacity-50"
          >
            {mutation.isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

export default function UsersPage() {
  const { me } = useAdminMe();
  const isGlobalAdmin = me?.is_global_admin;

  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selectedOrgId, setSelectedOrgId] = useState(null);
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [editUser, setEditUser] = useState(null);

  const { data: orgs } = useQuery("onboarded-orgs", getOrganizations, {
    enabled: !!isGlobalAdmin,
  });

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const handleOrgChange = useCallback((orgId) => {
    setSelectedOrgId(orgId);
    setPage(1);
  }, []);

  const { data: stats } = useQuery(
    ["admin-user-stats", selectedOrgId],
    () => getAdminUserStats(selectedOrgId || undefined),
    { keepPreviousData: true },
  );

  const { data, isLoading } = useQuery(
    ["admin-users", debouncedSearch, selectedOrgId, page],
    () =>
      getAdminUsers({
        q: debouncedSearch,
        orgId: selectedOrgId || undefined,
        page,
        pageSize: PAGE_SIZE,
      }),
    { keepPreviousData: true },
  );

  const handleExport = async () => {
    setExporting(true);
    try {
      await exportUsersCSV({ q: debouncedSearch, orgId: selectedOrgId || undefined });
    } finally {
      setExporting(false);
    }
  };

  const results = data?.results || [];
  const total = data?.total || 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Admin &middot; Users
          </p>
          <h2 className="text-xl font-semibold text-foreground mt-0.5">
            Users &amp; Access
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {isGlobalAdmin && (
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-2 px-4 py-2 bg-new-button-bg rounded-lg text-sm font-semibold text-foreground hover-button"
            >
              <Plus className="w-4 h-4" strokeWidth={2} />
              Create User
            </button>
          )}
          <button
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-2 px-4 py-2 border border-border rounded-lg text-sm font-medium text-foreground hover:bg-accent transition-colors disabled:opacity-50"
          >
            {exporting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Download className="w-4 h-4" strokeWidth={1.5} />
            )}
            Export CSV
          </button>
        </div>
      </div>

      {/* Stats strip */}
      {stats && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          {[
            { label: "Total Users", value: stats.total_users },
            { label: "Master Admins", value: stats.master_admins },
            { label: "Active", value: stats.active },
            { label: "Groups", value: stats.groups },
          ].map((s) => (
            <div
              key={s.label}
              className="border border-border rounded-lg px-4 py-3 bg-white"
            >
              <p className="text-2xl font-semibold text-foreground">{s.value}</p>
              <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide mt-0.5">
                {s.label}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Filters row */}
      <div className="flex items-center gap-4 mb-4">
        <div className="relative max-w-xs flex-1">
          <Search
            className="absolute left-3 top-2.5 w-4 h-4 text-muted-foreground"
            strokeWidth={1.5}
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name or email..."
            className="w-full pl-9 pr-3 py-2 border border-border rounded-lg text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        {isGlobalAdmin && orgs && orgs.length > 0 && (
          <select
            value={selectedOrgId || ""}
            onChange={(e) =>
              handleOrgChange(e.target.value ? Number(e.target.value) : null)
            }
            className="text-sm border border-border rounded-lg px-3 py-2 bg-white text-foreground"
          >
            <option value="">All Organizations</option>
            {orgs.map((o) => (
              <option key={o.id} value={o.id}>
                {o.org_name}
              </option>
            ))}
          </select>
        )}

        {!isGlobalAdmin && me?.org && (
          <span className="text-sm text-muted-foreground flex items-center gap-1.5">
            <Building2 className="w-3.5 h-3.5" strokeWidth={1.5} />
            {me.org.org_name}
          </span>
        )}
      </div>

      {/* Table */}
      {isLoading && !data ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : results.length > 0 ? (
        <>
          <div className="rounded-lg overflow-hidden border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-new-table-header-bg">
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">
                    User
                  </th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">
                    Organization
                  </th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">
                    Role
                  </th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">
                    Groups
                  </th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">
                    Folder Access
                  </th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-border">
                {results.map((u) => {
                  const isMasterAdmin = isGlobalRole(u.role_label);
                  const isOrgAdmin = u.role_label === "admin";
                  const b = ROLE_BADGES[u.role_label] || ROLE_BADGES.user;

                  return (
                    <tr
                      key={u.id}
                      onClick={() => setSelectedUserId(u.id)}
                      className="hover:bg-new-bg-light/50 transition-colors cursor-pointer"
                    >
                      {/* User */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-new-bg flex items-center justify-center text-foreground text-xs font-semibold flex-shrink-0">
                            {(u.user_name || u.email || "?")
                              .charAt(0)
                              .toUpperCase()}
                          </div>
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-foreground truncate">
                              {u.user_name || "—"}
                            </p>
                            <p className="text-xs text-muted-foreground truncate">
                              {u.email || "—"}
                            </p>
                          </div>
                        </div>
                      </td>

                      {/* Organization */}
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {isMasterAdmin ? "—" : u.org_name || "—"}
                      </td>

                      {/* Role */}
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block text-[11px] font-semibold px-2.5 py-0.5 rounded-full whitespace-nowrap ${b.cls}`}
                        >
                          {b.label}
                        </span>
                      </td>

                      {/* Groups */}
                      <td className="px-4 py-3">
                        {isMasterAdmin ? (
                          <span className="text-xs text-muted-foreground">—</span>
                        ) : (u.groups_total || u.groups.length) > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {u.groups.slice(0, 2).map((g) => (
                              <span
                                key={g.id}
                                className="inline-flex items-center gap-1 text-[11px] font-medium bg-new-bg rounded-full px-2 py-0.5 text-foreground"
                              >
                                <Users
                                  className="w-3 h-3"
                                  strokeWidth={1.5}
                                />
                                {g.name}
                              </span>
                            ))}
                            {(u.groups_total || u.groups.length) > 2 && (
                              <span className="inline-flex items-center text-[11px] font-medium bg-blue-50 text-blue-600 rounded-full px-2 py-0.5">
                                +{(u.groups_total || u.groups.length) - 2}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>

                      {/* Folder Access */}
                      <td className="px-4 py-3">
                        {isMasterAdmin ? (
                          <span className="text-xs text-muted-foreground">—</span>
                        ) : isOrgAdmin ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-mono text-muted-foreground italic">
                            (all org folders)
                            <span className="font-sans font-semibold text-green-600 not-italic">
                              RW
                            </span>
                          </span>
                        ) : (u.folder_access_total || u.folder_access.length) > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {u.folder_access.slice(0, 2).map((fa, i) => (
                              <span
                                key={i}
                                className="inline-flex items-center gap-1 text-[11px] bg-gray-50 border border-border rounded px-1.5 py-0.5 font-mono text-muted-foreground"
                              >
                                <FolderKey
                                  className="w-3 h-3"
                                  strokeWidth={1.5}
                                />
                                {fa.prefix}
                                <span
                                  className={`ml-0.5 font-sans font-semibold ${
                                    fa.access_level === "read_write"
                                      ? "text-green-600"
                                      : "text-blue-600"
                                  }`}
                                >
                                  {fa.access_level === "read_write" ? "RW" : "R"}
                                </span>
                              </span>
                            ))}
                            {(u.folder_access_total || u.folder_access.length) > 2 && (
                              <span className="inline-flex items-center text-[11px] font-medium bg-blue-50 text-blue-600 rounded-full px-2 py-0.5">
                                +{(u.folder_access_total || u.folder_access.length) - 2}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>

                      {/* Status */}
                      <td className="px-4 py-3">
                        {u.active ? (
                          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-green-700">
                            <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                            Active
                          </span>
                        ) : !isAccountActive(u) ? (
                          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                            <span className="w-1.5 h-1.5 rounded-full bg-gray-300" />
                            Inactive (account)
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-xs text-amber-700">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                            Inactive (S3)
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between mt-4 text-sm text-muted-foreground">
            <p>
              Showing {(page - 1) * PAGE_SIZE + 1}–
              {Math.min(page * PAGE_SIZE, total)} of {total}
            </p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1.5 rounded hover:bg-accent disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-2 text-foreground font-medium">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-1.5 rounded hover:bg-accent disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </>
      ) : (
        <div className="border border-dashed border-border rounded-lg py-16 flex flex-col items-center text-center">
          <UserCircle
            className="w-10 h-10 text-muted-foreground mb-3"
            strokeWidth={1}
          />
          <p className="text-foreground font-medium">No users found</p>
          <p className="text-sm text-muted-foreground mt-1 max-w-sm">
            {debouncedSearch
              ? `No users match "${debouncedSearch}".`
              : "No users are available for this organization."}
          </p>
        </div>
      )}

      {/* Detail Panel */}
      {selectedUserId && (
        <UserDetailPanel
          userId={selectedUserId}
          onClose={() => setSelectedUserId(null)}
          onDeactivated={() => setSelectedUserId(null)}
          onEdit={(detail) => setEditUser(detail)}
        />
      )}

      {showCreate && (
        <CreateUserModal orgs={orgs} onClose={() => setShowCreate(false)} />
      )}

      {editUser && (
        <EditUserModal
          user={editUser}
          orgs={orgs}
          onClose={() => setEditUser(null)}
        />
      )}
    </div>
  );
}
