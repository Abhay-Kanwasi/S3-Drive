"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { setSelectedUserId } from "@/services/auth";

export default function LoginPage() {
  const [userId, setUserId] = useState("");
  const [error, setError] = useState("");
  const router = useRouter();

  const handleSubmit = (e) => {
    e.preventDefault();
    const id = String(userId || "").trim();
    if (!id || !/^\d+$/.test(id)) {
      setError("Please enter a valid numeric user ID");
      return;
    }
    setSelectedUserId(id);
    router.push("/explorer");
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-card rounded-xl shadow-lg p-8 space-y-6">
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-accent-subtle text-accent mb-4">
            <span className="text-2xl font-bold">SD</span>
          </div>
          <h1 className="text-2xl font-semibold text-foreground">S3 Drive</h1>
          <p className="text-sm text-muted-foreground mt-2">
            Select a user to continue
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              User ID
            </label>
            <input
              type="text"
              inputMode="numeric"
              value={userId}
              onChange={(e) => {
                setUserId(e.target.value);
                setError("");
              }}
              placeholder="e.g. 1 (admin) or 2 (user)"
              className={`w-full px-4 py-3 rounded-lg border ${
                error ? "border-destructive" : "border-border"
              } bg-background text-foreground outline-none focus:ring-2 focus:ring-ring`}
            />
            {error && (
              <p className="text-destructive text-xs mt-2">{error}</p>
            )}
          </div>

          <button
            type="submit"
            className="w-full py-3 px-4 bg-accent hover:bg-accent-hover text-white font-semibold rounded-lg transition-colors"
          >
            Continue
          </button>
        </form>

        <div className="text-center text-xs text-muted-foreground">
          <p>Dev mode - X-User-Id header authentication</p>
        </div>
      </div>
    </div>
  );
}
