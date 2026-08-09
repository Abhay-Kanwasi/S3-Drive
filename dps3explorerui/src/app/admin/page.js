"use client";
import { useState, useMemo, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "react-query";
import { Database, Plus, Loader2, Search, Unlink } from "lucide-react";
import UnonboardModal from "./UnonboardModal";
import {
  getOrganizations,
  getAvailableBuckets,
  createOrganization,
} from "@/services/admin";
import { useAdminMe } from "./AdminContext";

export default function AdminPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showWizard, setShowWizard] = useState(false);
  const [unonboardTarget, setUnonboardTarget] = useState(null);
  const { me } = useAdminMe();
  const isGlobalAdmin = me?.is_global_admin;

  useEffect(() => {
    if (me && !isGlobalAdmin) {
      router.replace("/admin/groups");
    }
  }, [me, isGlobalAdmin]);

  const { data: orgs, isLoading } = useQuery("onboarded-orgs", getOrganizations);

  return (
    <div className="max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-foreground">Onboarded Buckets</h2>
          <p className="text-xs text-muted-foreground mt-1">
            {orgs?.length || 0} organizations &middot; {orgs?.length || 0} buckets binding
          </p>
        </div>
        {isGlobalAdmin && (
          <button
            onClick={() => setShowWizard(true)}
            className="flex items-center gap-2 px-4 py-2 bg-new-button-bg rounded-lg text-sm font-semibold text-foreground hover-button"
          >
            <Plus className="w-4 h-4" strokeWidth={2} />
            Add S3 Bucket
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : orgs && orgs.length > 0 ? (
        <div className="rounded-lg overflow-hidden border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-new-table-header-bg">
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">Organization</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">Org key</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">Bucket Name</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">Region</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">Status</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">Onboarded</th>
                <th className="w-28"></th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-border">
              {orgs.map((org) => (
                <tr key={org.id} className="hover:bg-new-bg-light/50 transition-colors">
                  <td className="px-4 py-3 font-medium text-foreground">{org.org_name}</td>
                  <td className="px-4 py-3 text-muted-foreground font-mono text-xs">{org.org_key || org.subscription_id || "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground font-mono text-xs">{org.bucket_name}</td>
                  <td className="px-4 py-3 text-muted-foreground">{org.region}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${
                      org.is_active ? "text-custom-green" : "text-dp-default"
                    }`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${org.is_active ? "bg-custom-green" : "bg-dp-default"}`} />
                      {org.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">
                    {org.created_at ? new Date(org.created_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "2-digit" }) : "—"}
                  </td>
                  <td className="px-4 py-3">
                    {isGlobalAdmin && org.is_active && (
                      <button
                        type="button"
                        onClick={() => setUnonboardTarget(org)}
                        className="inline-flex items-center gap-1 text-xs font-medium text-destructive border border-destructive/30 rounded-lg px-2.5 py-1 hover:bg-destructive/5"
                      >
                        <Unlink className="w-3 h-3" strokeWidth={1.5} />
                        Un-onboard
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="border border-dashed border-border rounded-lg py-16 flex flex-col items-center text-center">
          <Database className="w-10 h-10 text-muted-foreground mb-3" strokeWidth={1} />
          <p className="text-foreground font-medium">No organizations onboarded</p>
          <p className="text-sm text-muted-foreground mt-1 max-w-sm">
            Create an organization and bind an S3 bucket to get started.
          </p>
          {isGlobalAdmin && (
            <button
              onClick={() => setShowWizard(true)}
              className="mt-4 px-4 py-2 bg-new-button-bg rounded-lg text-sm font-semibold text-foreground hover-button"
            >
              Get Started
            </button>
          )}
        </div>
      )}

      {showWizard && <OnboardWizard onClose={() => setShowWizard(false)} />}

      {unonboardTarget && (
        <UnonboardModal
          org={unonboardTarget}
          onClose={() => setUnonboardTarget(null)}
          onSubmitted={() => queryClient.invalidateQueries("onboarded-orgs")}
        />
      )}
    </div>
  );
}

function OnboardWizard({ onClose }) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState(1);
  const [orgKey, setOrgKey] = useState("");
  const [orgName, setOrgName] = useState("");
  const [selectedBucket, setSelectedBucket] = useState(null);
  const [bucketSearch, setBucketSearch] = useState("");
  const [error, setError] = useState("");

  const { data: buckets, isLoading: loadingBuckets } = useQuery(
    "available-buckets",
    getAvailableBuckets
  );

  const filteredBuckets = useMemo(() => {
    if (!buckets) return [];
    if (!bucketSearch) return buckets;
    const q = bucketSearch.toLowerCase();
    return buckets.filter((b) => b.name.toLowerCase().includes(q));
  }, [buckets, bucketSearch]);

  const mutation = useMutation(createOrganization, {
    onSuccess: () => {
      queryClient.invalidateQueries("onboarded-orgs");
      queryClient.invalidateQueries("available-buckets");
      onClose();
    },
    onError: (err) => {
      setError(err.message);
    },
  });

  const handleSubmit = () => {
    if (!orgKey.trim() || !orgName.trim() || !selectedBucket) return;
    setError("");
    mutation.mutate({
      org_key: orgKey.trim(),
      org_name: orgName.trim(),
      bucket_name: selectedBucket.name,
    });
  };

  const canNext =
    orgKey.trim().length > 0 && orgName.trim().length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black-alpha" onClick={onClose} />
      <div className="relative bg-white rounded-xl shadow-lg border border-border w-full max-w-md mx-4">
        <div className="px-6 pt-5 pb-3">
          <p className="text-[11px] font-semibold text-new-bg uppercase tracking-wide mb-1">
            Step {step} of 2
          </p>
          <h3 className="text-base font-semibold text-foreground">
            {step === 1 ? "Add S3 Bucket — Organization" : "Choose S3 Bucket"}
          </h3>
          {step === 2 && (
            <p className="text-xs text-muted-foreground mt-1">
              Shows buckets in the AWS account that are not bound to any organization.
            </p>
          )}
        </div>

        <div className="px-6 pb-4 min-h-[280px]">
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide block mb-1.5">
                  Org key
                </label>
                <input
                  type="text"
                  value={orgKey}
                  onChange={(e) => setOrgKey(e.target.value)}
                  placeholder="stable-external-id"
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm text-foreground focus:outline-none focus:border-new-bg placeholder:text-muted-foreground/50 font-mono"
                  autoFocus
                />
                <p className="text-[11px] text-muted-foreground mt-1.5">
                  Unique stable identifier for this organization.
                </p>
              </div>
              <div>
                <label className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide block mb-1.5">
                  Organization name
                </label>
                <input
                  type="text"
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  placeholder="Acme Corp"
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm text-foreground focus:outline-none focus:border-new-bg placeholder:text-muted-foreground/50"
                />
              </div>
            </div>
          )}

          {step === 2 && (
            <div>
              <div className="relative mb-3">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <input
                  type="text"
                  value={bucketSearch}
                  onChange={(e) => setBucketSearch(e.target.value)}
                  placeholder="Search buckets..."
                  className="w-full pl-8 pr-3 py-2 border border-border rounded-lg text-sm text-foreground focus:outline-none focus:border-new-bg placeholder:text-muted-foreground/50"
                />
              </div>
              {loadingBuckets ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                </div>
              ) : filteredBuckets.length > 0 ? (
                <div className="max-h-52 overflow-y-auto border border-border rounded-lg divide-y divide-border">
                  {filteredBuckets.map((bucket) => (
                    <label
                      key={bucket.name}
                      className={`flex items-center gap-3 px-3 py-2.5 cursor-pointer transition-colors ${
                        selectedBucket?.name === bucket.name
                          ? "bg-new-bg-light"
                          : "hover:bg-accent"
                      }`}
                    >
                      <Database className="w-4 h-4 text-custom-gray flex-shrink-0" strokeWidth={1.5} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-foreground truncate">{bucket.name}</p>
                        <p className="text-[11px] text-muted-foreground">{bucket.region}</p>
                      </div>
                      <input
                        type="radio"
                        name="bucket"
                        className="accent-new-bg w-3.5 h-3.5 flex-shrink-0"
                        checked={selectedBucket?.name === bucket.name}
                        onChange={() => setSelectedBucket(bucket)}
                      />
                    </label>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground py-6 text-center">
                  {bucketSearch ? "No matching buckets." : "No available buckets."}
                </p>
              )}
            </div>
          )}

          {error && (
            <div className="mt-3 p-2.5 bg-dp-default-light rounded-lg">
              <p className="text-xs text-dp-default">{error}</p>
            </div>
          )}
        </div>

        <div className="px-6 py-3.5 border-t border-border flex justify-between items-center">
          <button
            onClick={step === 1 ? onClose : () => setStep(1)}
            className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            {step === 1 ? "Cancel" : "← Back"}
          </button>
          <button
            onClick={step === 1 ? () => setStep(2) : handleSubmit}
            disabled={
              (step === 1 && !canNext) ||
              (step === 2 && !selectedBucket) ||
              mutation.isLoading
            }
            className="px-5 py-2 bg-new-button-bg rounded-lg text-sm font-semibold text-foreground hover-button disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none flex items-center gap-2"
          >
            {mutation.isLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {step === 1 ? "Next →" : "Confirm"}
          </button>
        </div>
      </div>
    </div>
  );
}
