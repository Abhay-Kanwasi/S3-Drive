"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getOnboardOrgs, submitOnboarding } from "@/services/auth";

function OnboardContent() {
  const router = useRouter();
  const params = useSearchParams();

  const token = params.get("token") || "";
  const email = params.get("email") || "";
  const googleName = params.get("name") || "";

  const [username, setUsername] = useState(googleName);
  const [orgId, setOrgId] = useState("");
  const [orgs, setOrgs] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) {
      router.replace("/login");
      return;
    }
    getOnboardOrgs().then(setOrgs).catch(() => setOrgs([]));
  }, [token, router]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim()) {
      setError("Name is required");
      return;
    }
    setError("");
    setLoading(true);
    try {
      await submitOnboarding({
        onboard_token: token,
        username: username.trim(),
        organization_id: orgId ? Number(orgId) : null,
      });
      router.replace("/");
    } catch (err) {
      setError(err.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-card rounded-xl shadow-lg p-8 space-y-6">
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-accent-subtle text-accent mb-4">
            <span className="text-2xl font-bold">SD</span>
          </div>
          <h1 className="text-2xl font-semibold text-foreground">Complete your profile</h1>
          <p className="text-sm text-muted-foreground mt-2">Just a few details to get you started</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">Email</label>
            <input
              type="email"
              value={email}
              readOnly
              className="w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm text-muted-foreground cursor-not-allowed"
            />
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">Name</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              readOnly={Boolean(googleName)}
              required
              placeholder="Your display name"
              className={`w-full rounded-lg border border-border px-3 py-2 text-sm ${
                googleName
                  ? "bg-muted text-muted-foreground cursor-not-allowed"
                  : "bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
              }`}
            />
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">
              Organization <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <select
              value={orgId}
              onChange={(e) => setOrgId(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
            >
              <option value="">Guest (no organization)</option>
              {orgs.map((o) => (
                <option key={o.id} value={o.id}>{o.org_name}</option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground">
              If you skip this, you&apos;ll be added as a guest user.
            </p>
          </div>

          {error && <p className="text-destructive text-sm">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50 transition"
          >
            {loading ? "Setting up your account…" : "Continue"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function OnboardPage() {
  return (
    <Suspense>
      <OnboardContent />
    </Suspense>
  );
}
