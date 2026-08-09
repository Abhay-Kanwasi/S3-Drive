"use client";
import { useState, useMemo, useContext } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "react-query";
import { Users, Plus, Loader2, Search, Trash2, X, Check, Building2 } from "lucide-react";
import { ApplicationContext } from "@/services/ContextProvider";
import { useAdminMe } from "../AdminContext";
import UserPicker from "./UserPicker";
import {
  getGroups,
  getOnboardedOrgs,
  createGroup,
} from "@/services/admin";
import GroupDeleteOtpModal from "./GroupDeleteOtpModal";

export default function GroupsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { currentOrg } = useContext(ApplicationContext);
  const [showWizard, setShowWizard] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [selectedOrgId, setSelectedOrgId] = useState(null);

  const { me } = useAdminMe();
  const { data: orgs } = useQuery("onboarded-orgs", getOnboardedOrgs);

  const isGlobalAdmin = me?.is_global_admin;

  const activeOrgId = isGlobalAdmin
    ? selectedOrgId || currentOrg?.id || orgs?.[0]?.id
    : me?.org?.id || currentOrg?.id || orgs?.[0]?.id;

  const { data: groups, isLoading } = useQuery(
    ["groups", activeOrgId],
    () => getGroups(activeOrgId),
    { enabled: !!activeOrgId },
  );

  return (
    <div className="max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-foreground">User Groups</h2>
          <p className="text-xs text-muted-foreground mt-1">
            {groups?.length || 0} groups
          </p>
        </div>
        <div className="flex items-center gap-3">
          {isGlobalAdmin && orgs && orgs.length > 1 && (
            <select
              value={activeOrgId || ""}
              onChange={(e) => setSelectedOrgId(Number(e.target.value))}
              className="text-sm border border-border rounded-lg px-3 py-2 bg-white text-foreground"
            >
              {orgs.map((o) => (
                <option key={o.id} value={o.id}>{o.org_name}</option>
              ))}
            </select>
          )}
          {!isGlobalAdmin && me?.org && (
            <span className="text-sm text-muted-foreground flex items-center gap-1.5">
              <Building2 className="w-3.5 h-3.5" strokeWidth={1.5} />
              {me.org.org_name}
            </span>
          )}
          <button
            onClick={() => setShowWizard(true)}
            disabled={!isGlobalAdmin && !activeOrgId}
            className="flex items-center gap-2 px-4 py-2 bg-new-button-bg rounded-lg text-sm font-semibold text-foreground hover-button disabled:opacity-50"
          >
            <Plus className="w-4 h-4" strokeWidth={2} />
            Create Group
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : groups && groups.length > 0 ? (
        <div className="rounded-lg overflow-hidden border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-new-table-header-bg">
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">Group Name</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">Members</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">Folder Grants</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">Created</th>
                <th className="w-10"></th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-border">
              {groups.map((g) => (
                <tr
                  key={g.id}
                  className="hover:bg-new-bg-light/50 transition-colors cursor-pointer"
                  onClick={() => router.push(`/admin/groups/${g.id}`)}
                >
                  <td className="px-4 py-3 font-medium text-foreground">{g.name}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    <span className="inline-flex items-center gap-1.5 text-xs font-medium bg-new-bg rounded-full px-2 py-0.5">
                      <Users className="w-3 h-3" strokeWidth={1.5} />
                      {g.member_count}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">{g.grant_count} folder{g.grant_count !== 1 ? "s" : ""}</td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">
                    {g.created_at ? new Date(g.created_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "2-digit" }) : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={(e) => { e.stopPropagation(); setDeleteTarget(g); }}
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
        <div className="border border-dashed border-border rounded-lg py-16 flex flex-col items-center text-center">
          <Users className="w-10 h-10 text-muted-foreground mb-3" strokeWidth={1} />
          <p className="text-foreground font-medium">No groups yet</p>
          <p className="text-sm text-muted-foreground mt-1 max-w-sm">
            Create a group to manage folder access for your team members.
          </p>
          <button
            onClick={() => setShowWizard(true)}
            disabled={!isGlobalAdmin && !activeOrgId}
            className="mt-4 px-4 py-2 bg-new-button-bg rounded-lg text-sm font-semibold text-foreground hover-button disabled:opacity-50"
          >
            Create First Group
          </button>
        </div>
      )}

      {showWizard && (
        <CreateGroupWizard
          isGlobalAdmin={isGlobalAdmin}
          fixedOrgId={isGlobalAdmin ? null : activeOrgId}
          orgs={orgs || []}
          onClose={() => setShowWizard(false)}
          onCreated={(createdOrgId) => {
            if (createdOrgId && createdOrgId !== activeOrgId) {
              setSelectedOrgId(createdOrgId);
            }
            queryClient.invalidateQueries(["groups"]);
          }}
        />
      )}

      {deleteTarget && activeOrgId && (
        <GroupDeleteOtpModal
          group={deleteTarget}
          orgId={activeOrgId}
          orgName={orgs?.find((o) => o.id === activeOrgId)?.org_name}
          onSuccess={() => {
            queryClient.invalidateQueries(["groups", activeOrgId]);
            setDeleteTarget(null);
          }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}


/**
 * Wizard flow depends on role:
 *   MASTER_ADMIN / SUPER_ADMIN (isGlobalAdmin=true):
 *     Step 1 — Select Organization
 *     Step 2 — Group Name (free-text)
 *     Step 3 — Pick Members from selected org
 *
 *   ORG_ADMIN (isGlobalAdmin=false, fixedOrgId set):
 *     Step 1 — Group Name (free-text)
 *     Step 2 — Pick Members from their org
 */
function CreateGroupWizard({ isGlobalAdmin, fixedOrgId, orgs, onClose, onCreated }) {
  const queryClient = useQueryClient();

  const STEP_ORG = "org";
  const STEP_NAME = "name";
  const STEP_MEMBERS = "members";

  const steps = isGlobalAdmin
    ? [STEP_ORG, STEP_NAME, STEP_MEMBERS]
    : [STEP_NAME, STEP_MEMBERS];

  const [stepIdx, setStepIdx] = useState(0);
  const currentStep = steps[stepIdx];
  const stepNumber = stepIdx + 1;
  const totalSteps = steps.length;

  const [wizardOrgId, setWizardOrgId] = useState(fixedOrgId);
  const [orgSearch, setOrgSearch] = useState("");
  const [groupName, setGroupName] = useState("");
  const [selectedUsers, setSelectedUsers] = useState([]);
  const [error, setError] = useState("");

  const activeOrgId = isGlobalAdmin ? wizardOrgId : fixedOrgId;

  const filteredOrgs = useMemo(() => {
    if (!orgs) return [];
    if (!orgSearch) return orgs;
    const q = orgSearch.toLowerCase();
    return orgs.filter(
      (o) => o.org_name.toLowerCase().includes(q) || o.bucket_name.toLowerCase().includes(q),
    );
  }, [orgs, orgSearch]);

  const mutation = useMutation(createGroup, {
    onSuccess: () => {
      onCreated(activeOrgId);
      onClose();
    },
    onError: (err) => setError(err.message),
  });

  const toggleUser = (u) => {
    setSelectedUsers((prev) => {
      const exists = prev.find((s) => s.id === u.id);
      return exists ? prev.filter((s) => s.id !== u.id) : [...prev, u];
    });
  };

  const handleNext = () => {
    setError("");
    if (currentStep === STEP_ORG && !wizardOrgId) {
      setError("Please select an organization");
      return;
    }
    if (currentStep === STEP_NAME && !groupName.trim()) {
      setError("Group name is required");
      return;
    }
    setStepIdx((i) => i + 1);
  };

  const handleBack = () => {
    setError("");
    if (stepIdx === 0) { onClose(); return; }
    setStepIdx((i) => i - 1);
  };

  const handleCreate = () => {
    if (!groupName.trim()) { setError("Group name required"); return; }
    mutation.mutate({
      org_id: activeOrgId,
      name: groupName.trim(),
      member_user_ids: selectedUsers.map((u) => u.id),
    });
  };

  const selectedOrgName = orgs?.find((o) => o.id === wizardOrgId)?.org_name;

  const stepTitle = currentStep === STEP_ORG
    ? "Select Organization"
    : currentStep === STEP_NAME
      ? "Group Name"
      : "Add Members";

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[80vh] flex flex-col">
        <div className="px-6 py-4 border-b border-border">
          <p className="text-[11px] font-semibold text-new-bg uppercase tracking-wide mb-1">
            Step {stepNumber} of {totalSteps}
          </p>
          <div className="flex items-center justify-between">
            <h3 className="text-base font-semibold text-foreground">
              Create Group — {stepTitle}
            </h3>
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
              <X className="w-4 h-4" />
            </button>
          </div>
          {currentStep === STEP_MEMBERS && selectedOrgName && isGlobalAdmin && (
            <p className="text-xs text-muted-foreground mt-1">
              Showing members of <span className="font-medium text-foreground">{selectedOrgName}</span>
            </p>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {/* ───── STEP: Select Organization (global admins only) ───── */}
          {currentStep === STEP_ORG && (
            <div>
              <label className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide block mb-1.5">
                Search organizations
              </label>
              <div className="relative mb-3">
                <Search className="absolute left-3 top-2.5 w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
                <input
                  type="text"
                  value={orgSearch}
                  onChange={(e) => setOrgSearch(e.target.value)}
                  placeholder="Search by name or bucket..."
                  className="w-full pl-9 pr-3 py-2 border border-border rounded-lg text-sm text-foreground outline-none"
                  autoFocus
                />
              </div>
              <div className="border border-border rounded-lg divide-y divide-border max-h-60 overflow-y-auto">
                {filteredOrgs.length > 0 ? (
                  filteredOrgs.map((o) => {
                    const isSelected = wizardOrgId === o.id;
                    return (
                      <button
                        key={o.id}
                        onClick={() => setWizardOrgId(o.id)}
                        className={`w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-new-bg-light/50 transition-colors ${
                          isSelected ? "bg-new-bg-light/80" : ""
                        }`}
                      >
                        <div className={`w-4 h-4 rounded-full border flex items-center justify-center ${
                          isSelected ? "bg-new-button-bg border-new-button-bg" : "border-border"
                        }`}>
                          {isSelected && <Check className="w-3 h-3 text-foreground" strokeWidth={2} />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-foreground truncate">{o.org_name}</p>
                          <p className="text-xs text-muted-foreground truncate font-mono">{o.bucket_name}</p>
                        </div>
                      </button>
                    );
                  })
                ) : (
                  <p className="text-sm text-muted-foreground text-center py-6">
                    {orgSearch ? "No matching organizations" : "No organizations available"}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* ───── STEP: Group Name ───── */}
          {currentStep === STEP_NAME && (
            <div>
              <label className="block text-sm font-medium text-foreground mb-2">
                Group name
              </label>
              <input
                type="text"
                value={groupName}
                onChange={(e) => { setGroupName(e.target.value); setError(""); }}
                placeholder="Analysts Team"
                className="w-full px-3 py-2.5 border border-border rounded-lg text-sm text-foreground outline-none"
                autoFocus
              />
              <p className="mt-2 text-xs text-muted-foreground">
                Use any clear name — no prefix required.
              </p>
              {isGlobalAdmin && selectedOrgName && (
                <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground bg-new-bg rounded-lg px-3 py-2">
                  <Building2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                  Organization: <span className="font-medium text-foreground">{selectedOrgName}</span>
                </div>
              )}
            </div>
          )}

          {/* ───── STEP: Pick Members ───── */}
          {currentStep === STEP_MEMBERS && activeOrgId && (
            <UserPicker
              orgId={activeOrgId}
              selectedUsers={selectedUsers}
              onToggle={toggleUser}
            />
          )}

          {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        </div>

        <div className="px-6 py-4 border-t border-border flex justify-between">
          <button
            onClick={handleBack}
            className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            {stepIdx === 0 ? "Cancel" : "Back"}
          </button>

          {currentStep === STEP_MEMBERS ? (
            <button
              onClick={handleCreate}
              disabled={mutation.isLoading}
              className="flex items-center gap-2 px-4 py-2 bg-new-button-bg rounded-lg text-sm font-semibold text-foreground hover-button disabled:opacity-50"
            >
              {mutation.isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
              Create Group {selectedUsers.length > 0 && `(${selectedUsers.length} members)`}
            </button>
          ) : (
            <button
              onClick={handleNext}
              className="px-4 py-2 bg-new-button-bg rounded-lg text-sm font-semibold text-foreground hover-button"
            >
              Next
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

