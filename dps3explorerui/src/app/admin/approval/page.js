"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, ShieldCheck, ShieldX, AlertCircle, LogIn } from "lucide-react";
import { getApprovalReview, submitApprovalDecision } from "@/services/admin";

const PARENT_APP_URL = process.env.NEXT_PUBLIC_PARENT_APP_URL || "";

export default function ApprovalReviewPage() {
  return (
    <Suspense fallback={<div className="flex justify-center items-center min-h-screen"><Loader2 className="animate-spin w-8 h-8 text-muted-foreground" /></div>}>
      <ApprovalReviewContent />
    </Suspense>
  );
}

function ApprovalReviewContent() {
  const router = useRouter();
  const params = useSearchParams();

  const id = params.get("id");
  const token = params.get("token");
  const action = params.get("action");

  const [review, setReview] = useState(null);
  const [reviewError, setReviewError] = useState("");
  const [reviewLoading, setReviewLoading] = useState(true);
  const [needsLogin, setNeedsLogin] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    if (!id || !token || !action) {
      setReviewError("Missing approval link parameters.");
      setReviewLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await getApprovalReview({
          id: Number(id),
          token,
          action,
        });
        if (!cancelled) setReview(data);
      } catch (e) {
        if (cancelled) return;
        if (e?.status === 401) {
          setNeedsLogin(true);
        } else {
          setReviewError(e?.message || "Failed to load approval");
        }
      } finally {
        if (!cancelled) setReviewLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, token, action]);

  const handleConfirm = async () => {
    if (submitting || result) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      const data = await submitApprovalDecision({
        id: Number(id),
        token,
        action,
      });
      setResult(data);
    } catch (e) {
      if (e?.status === 401) {
        setNeedsLogin(true);
      } else {
        setSubmitError(e?.message || "Failed to submit");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleSignIn = () => {
    if (PARENT_APP_URL) {
      window.location.href = PARENT_APP_URL;
    }
  };

  if (reviewLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (needsLogin) {
    return (
      <div className="max-w-xl mx-auto">
        <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-5 flex gap-3">
          <LogIn className="w-6 h-6 text-blue-700 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-blue-900">
              Please sign in to approve this request
            </p>
            <p className="text-sm text-blue-900/80 mt-1">
              Sign in with the approver&apos;s DataPoem account in this browser,
              then re-open the approval link from your email. Only the master
              admin selected as approver can approve or reject.
            </p>
            {PARENT_APP_URL && (
              <button
                onClick={handleSignIn}
                className="mt-3 px-3 py-1.5 text-xs font-semibold rounded-md bg-blue-600 text-white hover:bg-blue-700"
              >
                Sign in to DataPoem
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (reviewError) {
    return (
      <div className="max-w-xl mx-auto">
        <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-4 flex gap-3">
          <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-amber-900">
              This approval link cannot be opened
            </p>
            <p className="text-sm text-amber-900/80 mt-1">{reviewError}</p>
            <button
              onClick={() => router.push("/admin/groups")}
              className="mt-3 text-xs text-amber-900 underline"
            >
              Go to admin home
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (result) {
    const ok = !result?.detail;
    return (
      <div className="max-w-xl mx-auto">
        <div
          className={`rounded-lg border p-5 flex gap-3 ${
            ok
              ? "border-green-200 bg-green-50/60"
              : "border-red-200 bg-red-50/60"
          }`}
        >
          {ok ? (
            <ShieldCheck className="w-6 h-6 text-green-700 flex-shrink-0 mt-0.5" />
          ) : (
            <ShieldX className="w-6 h-6 text-red-700 flex-shrink-0 mt-0.5" />
          )}
          <div>
            <p
              className={`text-sm font-semibold ${
                ok ? "text-green-900" : "text-red-900"
              }`}
            >
              {result.title || (ok ? "Done" : "Could not complete")}
            </p>
            <p
              className={`text-sm mt-1 ${
                ok ? "text-green-900/80" : "text-red-900/80"
              }`}
            >
              {result.message || result.detail || ""}
            </p>
            <button
              onClick={() => router.push("/admin/groups")}
              className="mt-4 px-3 py-1.5 text-xs font-semibold rounded-md bg-new-button-bg text-foreground hover-button"
            >
              Back to Groups
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!review) return null;

  const isApprove = review.action === "approve";
  const summary = review.summary || {};
  const isUnonboard = review.kind === "unonboard";

  const title = isUnonboard
    ? isApprove
      ? "Confirm un-onboard"
      : "Reject un-onboard"
    : isApprove
      ? "Confirm group deletion"
      : "Reject group deletion";

  return (
    <div className="max-w-xl mx-auto space-y-5">
      <div>
        <p className="text-[11px] font-semibold text-amber-800 uppercase tracking-wide mb-1">
          Sensitive action · 4-eyes approval
        </p>
        <h1 className="text-xl font-semibold text-foreground">{title}</h1>
      </div>

      <p className="text-sm text-muted-foreground">
        <strong>{review.requester_label}</strong>{" "}
        {isApprove
          ? isUnonboard
            ? "asked you to approve un-onboarding this organization. The org–bucket binding and all Explorer groups/grants will be removed. The S3 bucket in AWS is not deleted."
            : "asked you to approve deleting this group. This cannot be undone."
          : isUnonboard
            ? "asked you to review an un-onboard request. Rejecting leaves the org–bucket binding unchanged."
            : "asked you to review a group deletion request. Rejecting will leave the group unchanged."}
      </p>

      <div className="rounded-lg border border-border bg-new-bg/40 p-4 text-sm space-y-2">
        {isUnonboard ? (
          <>
            <Row label="Organization" value={summary.org_name} bold />
            <Row label="Bucket" value={summary.bucket_name} mono />
            <Row label="Grants to revoke" value={summary.grant_count} />
            <Row label="Groups (will be removed)" value={summary.group_count} />
          </>
        ) : (
          <>
            <Row label="Group" value={summary.group_name} bold />
            <Row label="Organization" value={summary.org_name} />
            <Row label="Members" value={summary.member_count} />
            <Row label="Folder grants" value={summary.grant_count} />
            {Array.isArray(summary.prefixes) && summary.prefixes.length > 0 && (
              <ul className="mt-2 ml-4 list-disc text-xs font-mono text-muted-foreground">
                {summary.prefixes.map((p) => (
                  <li key={p}>{p}</li>
                ))}
                {summary.grant_count > summary.prefixes.length && (
                  <li className="font-sans not-italic">
                    +{summary.grant_count - summary.prefixes.length} more
                  </li>
                )}
              </ul>
            )}
          </>
        )}
      </div>

      <div className="rounded-md border border-amber-200 bg-amber-50/60 px-3 py-2">
        <p className="text-xs text-amber-900">
          <strong>4-eyes verification:</strong> Only the designated approver can confirm this action.
          The requester cannot approve their own request.
        </p>
      </div>

      {submitError && (
        <div className="rounded-md border border-red-200 bg-red-50/60 px-3 py-2 text-sm text-red-900">
          {submitError}
        </div>
      )}

      <div className="pt-2 border-t border-border">
        <p className="text-[11px] text-muted-foreground mb-3">
          No changes are made until you click confirm.
        </p>
        <div className="flex gap-2">
          <button
            onClick={() => router.push("/admin/groups")}
            disabled={submitting}
            className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={submitting}
            className={`px-4 py-2 text-sm font-semibold rounded-lg text-white disabled:opacity-50 flex items-center gap-2 ${
              isApprove ? "bg-green-600 hover:bg-green-700" : "bg-red-600 hover:bg-red-700"
            }`}
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {isApprove
              ? isUnonboard
                ? "Confirm un-onboard"
                : "Confirm deletion"
              : "Confirm rejection"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, bold, mono }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span
        className={`${bold ? "font-semibold" : ""} ${mono ? "font-mono text-xs" : ""}`}
      >
        {value ?? "—"}
      </span>
    </div>
  );
}
