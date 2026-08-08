"use client";
import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "react-query";
import {
  ArrowLeft, Users, FolderOpen, Settings, Plus, Trash2,
  Loader2, X, Pencil,
} from "lucide-react";
import {
  getGroupDetail,
  renameGroup,
  addMembers,
  removeMember,
  removeGrant,
} from "@/services/admin";
import UserPicker from "../UserPicker";
import FolderMappingModal from "./FolderMappingModal";
import GroupDeleteOtpModal from "../GroupDeleteOtpModal";

export default function GroupDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const groupId = Number(id);

  const [activeTab, setActiveTab] = useState("members");
  const [showAddMembers, setShowAddMembers] = useState(false);
  const [showFolderMapping, setShowFolderMapping] = useState(false);
  const [showRename, setShowRename] = useState(false);
  const [showDelete, setShowDelete] = useState(false);

  const { data: group, isLoading } = useQuery(
    ["group-detail", groupId],
    () => getGroupDetail(groupId),
    { enabled: !!groupId },
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!group) {
    return <p className="text-muted-foreground">Group not found.</p>;
  }

  const tabs = [
    { id: "members", label: "Members", icon: Users, count: group.members.length },
    { id: "grants", label: "Folder Grants", icon: FolderOpen, count: group.grants.length },
    { id: "settings", label: "Settings", icon: Settings },
  ];

  return (
    <div className="max-w-5xl">
      <button
        onClick={() => router.push("/admin/groups")}
        className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-4"
      >
        <ArrowLeft className="w-4 h-4" strokeWidth={1.5} />
        Back to Groups
      </button>

      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-foreground">{group.name}</h2>
          <p className="text-xs text-muted-foreground mt-1">
            {group.members.length} members · {group.grants.length} folder grants
          </p>
        </div>
      </div>

      <div className="flex gap-1 mb-6 border-b border-border">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                isActive
                  ? "border-foreground text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              <Icon className="w-4 h-4" strokeWidth={1.5} />
              {tab.label}
              {tab.count !== undefined && (
                <span className="text-xs bg-new-bg rounded-full px-1.5 py-0.5">{tab.count}</span>
              )}
            </button>
          );
        })}
      </div>

      {activeTab === "members" && (
        <MembersTab
          group={group}
          groupId={groupId}
          showAddMembers={showAddMembers}
          setShowAddMembers={setShowAddMembers}
        />
      )}
      {activeTab === "grants" && (
        <GrantsTab
          group={group}
          groupId={groupId}
          showFolderMapping={showFolderMapping}
          setShowFolderMapping={setShowFolderMapping}
        />
      )}
      {activeTab === "settings" && (
        <SettingsTab
          group={group}
          groupId={groupId}
          showRename={showRename}
          setShowRename={setShowRename}
          showDelete={showDelete}
          setShowDelete={setShowDelete}
        />
      )}
    </div>
  );
}

function MembersTab({ group, groupId, showAddMembers, setShowAddMembers }) {
  const queryClient = useQueryClient();

  const removeMut = useMutation(
    (userId) => removeMember(groupId, userId),
    { onSuccess: () => queryClient.invalidateQueries(["group-detail", groupId]) },
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-muted-foreground">{group.members.length} members</p>
        <button
          onClick={() => setShowAddMembers(true)}
          className="flex items-center gap-2 px-3 py-1.5 bg-new-button-bg rounded-lg text-xs font-semibold text-foreground hover-button"
        >
          <Plus className="w-3.5 h-3.5" strokeWidth={2} />
          Add Members
        </button>
      </div>

      {group.members.length > 0 ? (
        <div className="rounded-lg overflow-hidden border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-new-table-header-bg">
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">User</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">Email</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">Added</th>
                <th className="w-10"></th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-border">
              {group.members.map((m) => (
                <tr key={m.id} className="hover:bg-new-bg-light/50 transition-colors">
                  <td className="px-4 py-3 font-medium text-foreground">{m.user_name || "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">{m.email || "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">
                    {m.added_at ? new Date(m.added_at).toLocaleDateString("en-US", { month: "short", day: "2-digit" }) : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => removeMut.mutate(m.user_id)}
                      disabled={removeMut.isLoading}
                      className="text-muted-foreground hover:text-destructive transition-colors p-1 rounded"
                    >
                      <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground text-center py-10">No members in this group yet.</p>
      )}

      {showAddMembers && (
        <AddMembersModal
          groupId={groupId}
          orgId={group.org_id}
          existingIds={group.members.map((m) => m.user_id)}
          onClose={() => setShowAddMembers(false)}
        />
      )}
    </div>
  );
}

function AddMembersModal({ groupId, orgId, existingIds, onClose }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState([]);

  const mutation = useMutation(
    () => addMembers(groupId, selected.map((u) => u.id)),
    {
      onSuccess: () => {
        queryClient.invalidateQueries(["group-detail", groupId]);
        onClose();
      },
    },
  );

  const toggle = (u) => {
    setSelected((prev) =>
      prev.find((s) => s.id === u.id) ? prev.filter((s) => s.id !== u.id) : [...prev, u],
    );
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md max-h-[70vh] flex flex-col">
        <div className="px-6 py-4 border-b border-border flex items-center justify-between">
          <h3 className="text-base font-semibold text-foreground">Add Members</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-4">
          <UserPicker
            orgId={orgId}
            selectedUsers={selected}
            onToggle={toggle}
            excludeIds={existingIds}
          />
        </div>
        <div className="px-6 py-4 border-t border-border flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground">
            Cancel
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={selected.length === 0 || mutation.isLoading}
            className="flex items-center gap-2 px-4 py-2 bg-new-button-bg rounded-lg text-sm font-semibold text-foreground hover-button disabled:opacity-50"
          >
            {mutation.isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
            Add {selected.length > 0 ? `(${selected.length})` : ""}
          </button>
        </div>
      </div>
    </div>
  );
}

function GrantsTab({ group, groupId, showFolderMapping, setShowFolderMapping }) {
  const queryClient = useQueryClient();

  const removeMut = useMutation(
    (grantId) => removeGrant(groupId, grantId),
    { onSuccess: () => queryClient.invalidateQueries(["group-detail", groupId]) },
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-muted-foreground">{group.grants.length} folder grants</p>
        <button
          onClick={() => setShowFolderMapping(true)}
          className="flex items-center gap-2 px-3 py-1.5 bg-new-button-bg rounded-lg text-xs font-semibold text-foreground hover-button"
        >
          <Plus className="w-3.5 h-3.5" strokeWidth={2} />
          Map Folder
        </button>
      </div>

      {group.grants.length > 0 ? (
        <div className="rounded-lg overflow-hidden border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-new-table-header-bg">
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">Folder Path</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">Access</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">Mapped</th>
                <th className="w-10"></th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-border">
              {group.grants.map((g) => (
                <tr key={g.id} className="hover:bg-new-bg-light/50 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-foreground">{g.prefix}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center text-xs font-medium rounded-full px-2 py-0.5 ${
                      g.access_level === "read_write"
                        ? "bg-blue-50 text-blue-700"
                        : "bg-gray-100 text-gray-600"
                    }`}>
                      {g.access_level === "read_write" ? "Read & Write" : "Read"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">
                    {g.created_at ? new Date(g.created_at).toLocaleDateString("en-US", { month: "short", day: "2-digit" }) : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => removeMut.mutate(g.id)}
                      disabled={removeMut.isLoading}
                      className="text-muted-foreground hover:text-destructive transition-colors p-1 rounded"
                    >
                      <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground text-center py-10">No folder grants mapped yet.</p>
      )}

      {showFolderMapping && (
        <FolderMappingModal
          groupId={groupId}
          orgId={group.org_id}
          onClose={() => setShowFolderMapping(false)}
        />
      )}
    </div>
  );
}

function SettingsTab({ group, groupId, showRename, setShowRename, showDelete, setShowDelete }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [newName, setNewName] = useState(group.name.replace(/^dp-/, ""));
  const [error, setError] = useState("");

  const renameMut = useMutation(
    (name) => renameGroup(groupId, name),
    {
      onSuccess: () => {
        queryClient.invalidateQueries(["group-detail", groupId]);
        setShowRename(false);
      },
      onError: (err) => setError(err.message),
    },
  );

  return (
    <div className="space-y-6 max-w-md">
      <div className="border border-border rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-medium text-foreground">Group Name</h4>
          {!showRename && (
            <button
              onClick={() => setShowRename(true)}
              className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
            >
              <Pencil className="w-3 h-3" /> Edit
            </button>
          )}
        </div>
        {showRename ? (
          <div>
            <div className="flex items-center border border-border rounded-lg overflow-hidden mb-2">
              <span className="px-3 py-2 bg-new-bg text-muted-foreground text-sm font-mono select-none">dp-</span>
              <input
                type="text"
                value={newName}
                onChange={(e) => { setNewName(e.target.value); setError(""); }}
                className="flex-1 px-3 py-2 text-sm text-foreground outline-none"
                autoFocus
              />
            </div>
            {error && <p className="text-xs text-destructive mb-2">{error}</p>}
            <div className="flex gap-2">
              <button
                onClick={() => renameMut.mutate(newName)}
                disabled={renameMut.isLoading || !newName.trim()}
                className="px-3 py-1.5 bg-new-button-bg rounded-lg text-xs font-semibold text-foreground hover-button disabled:opacity-50"
              >
                Save
              </button>
              <button
                onClick={() => { setShowRename(false); setNewName(group.name.replace(/^dp-/, "")); }}
                className="px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-foreground font-mono">{group.name}</p>
        )}
      </div>

      <div className="border border-destructive/30 rounded-lg p-4">
        <h4 className="text-sm font-medium text-destructive mb-1">Danger Zone</h4>
        <p className="text-xs text-muted-foreground mb-3">
          Deleting this group will remove all member associations and folder grants.
        </p>
        <button
          onClick={() => setShowDelete(true)}
          className="px-3 py-1.5 border border-destructive/30 text-destructive rounded-lg text-xs font-medium hover:bg-destructive/5"
        >
          Delete Group
        </button>
      </div>

      {showDelete && (
        <GroupDeleteOtpModal
          group={group}
          orgId={group.org_id}
          orgName={group.org_name}
          onSuccess={() => {
            queryClient.invalidateQueries(["groups"]);
            router.push("/admin/groups");
          }}
          onCancel={() => setShowDelete(false)}
        />
      )}
    </div>
  );
}
