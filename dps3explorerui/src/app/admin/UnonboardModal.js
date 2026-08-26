"use client";

import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation } from "react-query";
import { Loader2, Mail, Search, Check, X } from "lucide-react";
import {
  getUnonboardApprovers,
  sendUnonboardOtp,
  submitUnonboardRequest,
} from "@/services/admin";

export default function UnonboardModal({ org, onClose, onSubmitted }) {
  const { data: approvers, isLoading: approversLoading } = useQuery(
    "unonboard-approvers",
    getUnonboardApprovers,
  );

  const [approverId, setApproverId] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [localError, setLocalError] = useState("");

  const sendOtpMutation = useMutation(() => sendUnonboardOtp(org.id), {
    onSuccess: () => {
      setOtpSent(true);
      setLocalError("");
    },
    onError: (err) => setLocalError(err.message),
  });

  const submitMutation = useMutation(
    () =>
      submitUnonboardRequest(org.id, {
        approver_user_id: Number(approverId),
        otp_code: otpCode.trim(),
      }),
    {
      onSuccess: () => {
        setSubmitted(true);
        setLocalError("");
      },
      onError: (err) => setLocalError(err.message),
    },
  );

  const busy = sendOtpMutation.isLoading || submitMutation.isLoading;
  const selectedApprover = approvers?.find(
    (a) => String(a.id) === String(approverId),
  );

  const handleSendOtp = () => {
    setLocalError("");
    sendOtpMutation.mutate();
  };

  const handleClose = () => {
    if (submitted) {
      onSubmitted?.();
    }
    onClose();
  };

  const handleSubmit = () => {
    if (!approverId) {
      setLocalError("Select a second master admin approver.");
      return;
    }
    if (!otpSent) {
      setLocalError("Send the verification code to your email first.");
      return;
    }
    if (!/^\d{6}$/.test(otpCode.trim())) {
      setLocalError("Enter the 6-digit code from your email.");
      return;
    }
    submitMutation.mutate();
  };

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/40" onClick={handleClose} />
      <div className="w-full max-w-md bg-white h-full shadow-2xl flex flex-col animate-slide-in-right">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            <p className="text-[11px] font-semibold text-status-warning uppercase tracking-wide">
              Sensitive action · 4-eyes approval
            </p>
            <h3 className="text-base font-semibold text-foreground">
              Un-onboard &ldquo;{org.org_name}&rdquo;
            </h3>
          </div>
          <button
            onClick={handleClose}
            disabled={busy}
            className="p-1 rounded hover:bg-gray-100 text-muted-foreground hover:text-foreground"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          <p className="text-sm text-muted-foreground">
            Removes the org–bucket binding and all Explorer groups, grants, and folder mappings.
            The S3 bucket and objects in AWS are not deleted; this subscriber and bucket can be
            onboarded again after approval. Requires a second master admin to approve by email.
          </p>

          <div className="rounded-lg border border-border bg-gray-100 p-3 text-sm space-y-1">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Bucket</span>
              <span className="font-mono text-xs">{org.bucket_name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Region</span>
              <span>{org.region}</span>
            </div>
          </div>

          {submitted ? (
            <div className="rounded-md bg-green-50 border border-green-200/80 px-3 py-3 text-sm text-green-900">
              <p className="font-medium">Request submitted</p>
              <p className="mt-1">
                An approval email was sent to{" "}
                <strong>{selectedApprover?.email}</strong> with Review and approve / reject
                links. The org stays active until they confirm on the confirmation page.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">
                  Your verification code (sent to your login email)
                </label>
                <p className="text-[11px] text-muted-foreground mb-1.5">
                  OTP goes to the account you are logged in as — not the approver.
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleSendOtp}
                    disabled={busy || otpSent}
                    className="shrink-0 flex items-center gap-1.5 px-3 py-2 border border-border rounded-lg text-xs font-medium disabled:opacity-50"
                  >
                    {sendOtpMutation.isLoading ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Mail className="w-3.5 h-3.5" />
                    )}
                    {otpSent ? "Code sent" : "Send code"}
                  </button>
                  <input
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    value={otpCode}
                    onChange={(e) =>
                      setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 6))
                    }
                    placeholder="6-digit OTP"
                    disabled={!otpSent}
                    className="flex-1 text-sm border border-border rounded-lg px-3 py-2 font-mono tracking-widest disabled:opacity-50"
                  />
                </div>
              </div>

              {approversLoading ? (
                <div className="flex justify-center py-2">
                  <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <ApproverSearch
                  approvers={approvers || []}
                  approverId={approverId}
                  onSelect={(id) => setApproverId(id)}
                />
              )}
            </div>
          )}

          {localError && (
            <p className="text-sm text-destructive">{localError}</p>
          )}
        </div>

        <div className="px-6 py-4 border-t border-border flex justify-end gap-2">
          <button
            type="button"
            onClick={handleClose}
            disabled={busy}
            className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground"
          >
            {submitted ? "Close" : "Cancel"}
          </button>
          {!submitted && (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={busy}
              className="px-4 py-2 bg-destructive text-white rounded-lg text-sm font-semibold disabled:opacity-50 flex items-center gap-2"
            >
              {submitMutation.isLoading && (
                <Loader2 className="w-4 h-4 animate-spin" />
              )}
              Submit request
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function ApproverSearch({ approvers, approverId, onSelect }) {
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
        Second master admin (approver)
      </label>
      <p className="text-[11px] text-muted-foreground mb-1.5">
        Approve/reject email goes to the person you select here (must be a different master admin).
      </p>
      <div className="relative">
        <div className="flex items-center border border-border rounded-lg bg-white overflow-hidden">
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
            className="flex-1 text-sm px-2 py-2 outline-none bg-transparent"
          />
        </div>
        {open && (
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
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-100/50 flex items-center justify-between ${
                    String(a.id) === String(approverId) ? "bg-accent-subtle" : ""
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
