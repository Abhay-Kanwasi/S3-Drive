"use client";
import { useContext, useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "react-query";
import { ApplicationContext } from "@/services/ContextProvider";
import { browseFolders, listAccessibleOrgs, getOrgStorage } from "@/services/browse";
import OrgSwitcher from "@/components/OrgSwitcher";
import StorageMeter from "@/components/StorageMeter";
import Trash from "@/components/trash";
import ShieldBadge from "@/components/ShieldBadge";
import { getOrgStats, setOrgStats, getRecentFiles } from "@/services/localStorage";
import {
  Settings, HardDrive,
  ChevronRight, ChevronDown, Folder, Clock3, Star,
} from "lucide-react";
import { useRouter } from "next/navigation";

// ─── Folder Tree ─────────────────────────────────────────────────────────────

function FolderTreeNode({ orgId, prefix, name, depth = 0, onNavigate }) {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useQuery(
    ["folder-tree", orgId, prefix],
    () => browseFolders(orgId, prefix),
    { enabled: open, staleTime: 30_000 }
  );

  const hasCustomPerms = false; // populated from data when available

  return (
    <div>
      <div
        className={`flex items-center gap-1.5 px-2 py-1.5 rounded-md cursor-pointer hover:bg-gray-100 text-sm text-sidebar-foreground transition-colors`}
        style={{ paddingLeft: `${(depth + 1) * 12}px` }}
        onClick={() => {
          setOpen((v) => !v);
          onNavigate(prefix, name);
        }}
      >
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
          className="shrink-0 text-muted-foreground"
        >
          {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        </button>
        <Folder className="w-4 h-4 shrink-0 text-status-warning" strokeWidth={1.5} />
        <span className="truncate flex-1">{name}</span>
        <ShieldBadge hasCustomPermissions={hasCustomPerms} />
      </div>
      {open && (
        <div>
          {isLoading && (
            <div className="text-xs text-muted-foreground pl-8 py-1">Loading…</div>
          )}
          {data?.folders?.map((f) => (
            <FolderTreeNode
              key={f.key}
              orgId={orgId}
              prefix={f.key}
              name={f.name}
              depth={depth + 1}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Quick Access ─────────────────────────────────────────────────────────────

function QuickAccess({ onRecent, onStarred }) {
  const recentFiles = getRecentFiles();
  
  return (
    <div className="mt-4">
      <p className="px-4 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
        Quick access
      </p>
      <button
        onClick={onRecent}
        className="w-full flex items-center gap-2.5 px-4 py-2 text-sm text-sidebar-foreground hover:bg-gray-100 rounded-md transition-colors"
      >
        <Clock3 className="w-4 h-4 shrink-0 text-muted-foreground" strokeWidth={1.5} />
        Recent
        {recentFiles.length > 0 && (
          <span className="ml-auto text-xs text-muted-foreground">{recentFiles.length}</span>
        )}
      </button>
      <button
        onClick={onStarred}
        className="w-full flex items-center gap-2.5 px-4 py-2 text-sm text-sidebar-foreground hover:bg-gray-100 rounded-md transition-colors"
      >
        <Star className="w-4 h-4 shrink-0 text-muted-foreground" strokeWidth={1.5} />
        Starred
      </button>
    </div>
  );
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────

export default function Sidebar() {
  const {
    path, setPath, setKeys,
    basePath, setBasePath,
    isAdmin, currentOrg, setCurrentOrg,
    setTag, setTrashView,
  } = useContext(ApplicationContext);

  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: storageData } = useQuery(
    ["org-storage", currentOrg?.id],
    () => getOrgStorage(currentOrg.id),
    { enabled: Boolean(currentOrg?.id), staleTime: 60_000, retry: false }
  );

  // Update localStorage with org stats when storage data changes
  useEffect(() => {
    if (currentOrg?.id && storageData) {
      setOrgStats(currentOrg.id, {
        fileCount: storageData.file_count ?? 0,
        members: 0, // TODO: fetch from backend when available
      });
    }
  }, [currentOrg?.id, storageData]);

  // Org list for OrgSwitcher
  const { data: orgsData } = useQuery("accessible-orgs", listAccessibleOrgs, {
    staleTime: 60_000, retry: false,
  });
  const orgs = Array.isArray(orgsData) ? orgsData.map((o) => ({
    id: o.org_id ?? o.id,
    name: o.org_name || o.folder_name || o.name || "Organization",
    org_name: o.org_name || o.folder_name || o.name || "Organization",
    role: o.role || o.role_label || "",
  })) : [];

  // Auto-select first org for non-admin users
  useEffect(() => {
    if (!isAdmin && orgsData && orgsData.length > 0 && !currentOrg?.id) {
      const firstOrg = orgsData[0];
      const mapped = {
        id: firstOrg.org_id ?? firstOrg.id,
        bucket_name: firstOrg.bucket_name,
        org_name: firstOrg.org_name || firstOrg.folder_name || firstOrg.name,
        max_upload_size_bytes: firstOrg.max_upload_size_bytes || 0,
      };
      setCurrentOrg(mapped);
      setPath(firstOrg.folder_path || "");
      setKeys(firstOrg.folder_name ? [firstOrg.folder_name] : []);
      setBasePath(firstOrg.folder_path || firstOrg.bucket_name || "");
    }
  }, [isAdmin, orgsData, currentOrg?.id, setCurrentOrg, setPath, setKeys, setBasePath]);

  const handleOrgSwitch = (orgId) => {
    const org = orgsData?.find((o) => String(o.org_id ?? o.id) === String(orgId));
    if (!org) return;
    const mapped = {
      id: org.org_id ?? org.id,
      bucket_name: org.bucket_name,
      org_name: org.org_name || org.folder_name || org.name,
      max_upload_size_bytes: org.max_upload_size_bytes || 0,
    };
    setCurrentOrg(mapped);
    setTag("explorer");
    setPath(org.folder_path || "");
    setKeys(org.folder_name ? [org.folder_name] : []);
    setBasePath(org.folder_path || org.bucket_name || "");
    setTrashView(false);
    queryClient.invalidateQueries(["contents"]);
  };

  const handleFolderNavigate = (prefix, name) => {
    setPath(prefix);
    const parts = prefix.replace(/\/$/, "").split("/").filter(Boolean);
    setKeys(parts);
    setTag("explorer");
    setTrashView(false);
  };

  return (
    <div className="bg-sidebar flex-shrink-0 w-64 h-full flex flex-col z-10 border-r border-sidebar-border">
      <div className="flex flex-col px-4 mx-2 pt-6 flex-1 overflow-y-auto">
        {/* Logo */}
        <div className="flex items-center gap-3 px-4 pb-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-subtle text-accent">
            <HardDrive className="h-5 w-5" strokeWidth={1.8} />
          </div>
          <p className="text-base font-semibold tracking-tight text-gray-900">S3 Drive</p>
        </div>

        {/* Org Switcher */}
        <div className="px-1 pb-3 border-b border-sidebar-border">
          {isAdmin ? (
            <OrgSwitcher
              orgs={orgs}
              activeOrgId={currentOrg?.id ? String(currentOrg.id) : ""}
              onSwitch={handleOrgSwitch}
            />
          ) : (
            <div className="w-full rounded-lg border border-border bg-card py-2 pl-3 pr-3 text-sm font-medium text-foreground">
              {currentOrg?.org_name || "Organization"}
            </div>
          )}
        </div>

        {/* Quick Access */}
        <QuickAccess
          onRecent={() => {}}
          onStarred={() => {}}
        />

        {/* Folder Tree */}
        {currentOrg?.id && (
          <div className="mt-4">
            <p className="px-4 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
              Folders
            </p>
            <FolderTreeNode
              orgId={currentOrg.id}
              prefix=""
              name={currentOrg.org_name || "Root"}
              depth={-1}
              onNavigate={handleFolderNavigate}
            />
          </div>
        )}
      </div>

      {/* Bottom section */}
      <div className="flex-shrink-0 px-4 mx-2 pb-4 space-y-2 border-t border-sidebar-border pt-3">
        {/* Storage meter */}
        <StorageMeter
          usedBytes={storageData?.used_bytes ?? 0}
          totalBytes={storageData?.total_bytes ?? currentOrg?.max_upload_size_bytes ?? 0}
        />

        <Trash />

        {isAdmin && (
          <button
            onClick={() => router.push("/admin")}
            className="w-full flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-gray-100 rounded-lg transition-colors"
          >
            <Settings className="w-4 h-4" strokeWidth={1.5} />
            Admin Panel
          </button>
        )}
      </div>
    </div>
  );
}
