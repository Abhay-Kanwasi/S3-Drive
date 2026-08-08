"use client";

import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation } from "react-query";
import { Loader2, Mail, Search, Check, X } from "lucide-react";
import { deleteGroup, getOtpApprovers, sendOtp } from "@/services/admin";

/**
 * Delete group — email Approve/Reject to approver when the group has folder grants.
 */
export default function GroupDeleteOtpModal({
  group,
  orgId,
  orgName,
  loading: externalLoading,
  onSuccess,
  onCancel,
}) {
  const memberCount =
    group.member_count ?? group.members?.length ?? 0;
  const grantCount =
    group.grant_count ?? group.grants?.length ?? 0;
  const grantPrefixes = (group.grants || [])
    .map((g) => g.prefix)
    .filter(Boolean);
  const needsApproval =
    grantCount > 0 || Boolean(group.requires_delete_approval);

  const { data: approvers, isLoading: approversLoading } = useQuery(
    ["otp-approvers", orgId],
    () => getOtpApprovers(orgId),
    { enabled: needsApproval && !!orgId },
  );

  const [approverId, setApproverId] = useState("");
  const [emailSent, setEmailSent] = useState(false);
  const [localError, setLocalError] = useState("");

  const sendMutation = useMutation(
    () =>
      sendOtp({
        purpose: `group_delete:${group.id}`,
        recipient_user_id: Number(approverId),
      }),
    {
      onSuccess: () => {
        setEmailSent(true);
        setLocalError("");
      },
      onError: (err) => setLocalError(err.message),
    },
  );

  const deleteMutation = useMutation(() => deleteGroup(group.id), {
    onSuccess: () => onSuccess?.(),
    onError: (err) => setLocalError(err.message),
  });

  const sendLoading = sendMutation.isLoading;
  const deleteLoading = externalLoading || deleteMutation.isLoading;
  const busy = sendLoading || deleteLoading;

  const selectedApprover = approvers?.find(
    (a) => String(a.id) === String(approverId),
  );

  const handleSendApproval = () => {
    if (!approverId) {
      setLocalError("Select an approver to send the approval email.");
      return;
    }
    sendMutation.mutate();
  };

  const handleDelete = () => {
    deleteMutation.mutate();
  };

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/40" onClick={onCancel} />
      <div className="w-full max-w-md bg-white h-full shadow-2xl flex flex-col animate-slide-in-right">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h3 className="text-base font-semibold text-foreground">
            Delete Group
          </h3>
          <button
            onClick={onCancel}
            disabled={busy}
            className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          <div className="rounded-lg border border-border bg-new-bg/40 p-3 space-y-2 text-sm">
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Group</span>
              <span className="font-semibold text-foreground text-right break-all">
                {group.name}
              </span>
            </div>
            {orgName && (
              <div className="flex justify-between gap-2">
                <span className="text-muted-foreground">Organization</span>
                <span className="text-foreground text-right">{orgName}</span>
              </div>
            )}
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Members</span>
              <span className="text-foreground font-medium">{memberCount}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Folder access</span>
              <span className="text-foreground font-medium">
                {grantCount} grant{grantCount !== 1 ? "s" : ""}
              </span>
            </div>
            {grantPrefixes.length > 0 && (
              <div className="pt-1 border-t border-border/60">
                <p className="text-xs text-muted-foreground mb-1">
                  Mapped prefixes
                </p>
                <ul className="text-xs text-foreground font-mono space-y-0.5 max-h-24 overflow-y-auto">
                  {grantPrefixes.slice(0, 8).map((p) => (
                    <li key={p} className="truncate">
                      {p}
                    </li>
                  ))}
                  {grantPrefixes.length > 8 && (
                    <li className="text-muted-foreground">
                      +{grantPrefixes.length - 8} more
                    </li>
                  )}
                </ul>
              </div>
            )}
          </div>

          <p className="text-sm text-muted-foreground">
            This permanently removes all members from the group
            {grantCount > 0
              ? " and revokes every folder grant listed above"
              : ""}
            . This cannot be undone.
          </p>

          {needsApproval ? (
            <div className="space-y-3 p-3 bg-amber-50/80 border border-amber-200/60 rounded-lg">
              <p className="text-xs text-amber-900">
                This group {grantCount > 0 ? `has ${grantCount} folder access mapping${grantCount !== 1 ? "s" : ""}` : "previously had folder access"}
                . Choose an approver — they will receive an email with{" "}
                <strong>Review and approve</strong> / <strong>Review and reject</strong>{" "}
                links. They confirm on a web page; the group is deleted only after
                they confirm approval.
              </p>

              {approversLoading ? (
                <div className="flex justify-center py-2">
                  <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <ApproverSearch
                  approvers={approvers || []}
                  approverId={approverId}
                  disabled={emailSent}
                  onSelect={(id) => {
                    setApproverId(id);
                    setEmailSent(false);
                    setLocalError("");
                  }}
                  label="Send approval email to"
                />
              )}

              {!emailSent ? (
                <button
                  type="button"
                  onClick={handleSendApproval}
                  disabled={sendLoading || !approverId || approversLoading}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 border border-border rounded-lg text-sm font-medium text-foreground hover:bg-new-bg disabled:opacity-50"
                >
                  {sendLoading && (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  )}
                  <Mail className="w-3.5 h-3.5" strokeWidth={1.5} />
                  Send approval email
                </button>
              ) : (
                <div className="rounded-md bg-white/80 border border-amber-200/80 px-3 py-2 text-xs text-amber-950">
                  <p className="font-medium">Approval email sent</p>
                  <p className="mt-1">
                    Waiting for{" "}
                    <strong>{selectedApprover?.email || "the approver"}</strong>{" "}
                    to click Approve or Reject in their inbox. Refresh the groups
                    list after they approve.
                  </p>
                </div>
              )}
            </div>
          ) : null}

          {localError && (
            <p className="text-sm text-destructive">{localError}</p>
          )}
        </div>

        <div className="px-6 py-4 border-t border-border flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
          >
            {emailSent ? "Close" : "Cancel"}
          </button>
          {!needsApproval && (
            <button
              type="button"
              onClick={handleDelete}
              disabled={deleteLoading}
              className="flex items-center gap-2 px-4 py-2 bg-destructive text-white rounded-lg text-sm font-semibold hover:bg-destructive/90 disabled:opacity-50"
            >
              {deleteLoading && <Loader2 className="w-4 h-4 animate-spin" />}
              Delete
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function ApproverSearch({ approvers, approverId, onSelect, disabled, label }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    const handleClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const filtered = approvers.filter((a) => {
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      a.email?.toLowerCase().includes(q) ||
      a.name?.toLowerCase().includes(q) ||
      a.role_label?.toLowerCase().includes(q)
    );
  });

  const selected = approvers.find((a) => String(a.id) === String(approverId));

  return (
    <div ref={containerRef}>
      <label className="block text-xs font-medium text-foreground mb-1">
        {label || "Select approver"}
      </label>
      <div className="relative">
        <div className={`flex items-center border border-border rounded-lg bg-white overflow-hidden ${disabled ? "opacity-60 pointer-events-none" : ""}`}>
          <Search className="w-4 h-4 text-muted-foreground ml-3 shrink-0" />
          <input
            type="text"
            value={open ? query : selected ? `${selected.email} (${selected.role_label})` : query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOpen(true);
            }}
            onFocus={() => {
              setOpen(true);
              if (selected) setQuery("");
            }}
            placeholder="Search by name or email…"
            disabled={disabled}
            className="flex-1 text-sm px-2 py-2 outline-none bg-transparent disabled:cursor-not-allowed"
          />
        </div>
        {open && !disabled && (
          <div className="absolute z-10 mt-1 w-full max-h-48 overflow-y-auto border border-border rounded-lg bg-white shadow-lg">
            {filtered.length === 0 ? (
              <div className="px-3 py-2 text-sm text-muted-foreground">No admins found</div>
            ) : (
              filtered.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => {
                    onSelect(String(a.id));
                    setQuery("");
                    setOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-accent/50 flex items-center justify-between ${
                    String(a.id) === String(approverId) ? "bg-accent/30" : ""
                  }`}
                >
                  <span>
                    {a.name && <span className="font-medium">{a.name} · </span>}
                    <span className="text-muted-foreground">{a.email}</span>
                    <span className="ml-1 text-xs text-muted-foreground">({a.role_label})</span>
                  </span>
                  {String(a.id) === String(approverId) && (
                    <Check className="w-4 h-4 text-green-600 shrink-0" />
                  )}
                </button>
              ))
            )}
          </div>
        )}
      </div>
      {selected && !open && (
        <p className="mt-1 text-xs text-green-700">
          ✓ {selected.email}
        </p>
      )}
    </div>
  );
}
