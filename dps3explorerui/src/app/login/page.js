"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { GoogleOAuthProvider, GoogleLogin } from "@react-oauth/google";
import { googleLogin } from "@/services/auth";

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

export default function LoginPage() {
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  if (!GOOGLE_CLIENT_ID) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <div className="w-full max-w-md rounded-xl bg-card p-8 text-center shadow-lg">
          <h1 className="text-xl font-semibold text-foreground">Google sign-in is not configured</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Set NEXT_PUBLIC_GOOGLE_CLIENT_ID and rebuild the UI container.
          </p>
        </div>
      </div>
    );
  }

  const handleSuccess = async (credentialResponse) => {
    setError("");
    setLoading(true);
    try {
      const data = await googleLogin(credentialResponse.credential);
      if (data.needs_onboarding) {
        const params = new URLSearchParams({
          token: data.onboard_token,
          email: data.email,
          name: data.name || "",
        });
        router.replace(`/onboard?${params.toString()}`);
        return;
      }
      router.replace("/");
    } catch (err) {
      setError(
        err.status === 401
          ? "No account found for this Google account. Contact your administrator."
          : err.status === 403
          ? "Your account has been deactivated. Contact your administrator."
          : err.message || "Login failed. Please try again."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <div className="w-full max-w-md bg-card rounded-xl shadow-lg p-8 space-y-6">
          <div className="text-center">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-accent-subtle text-accent mb-4">
              <span className="text-2xl font-bold">SD</span>
            </div>
            <h1 className="text-2xl font-semibold text-foreground">S3 Drive</h1>
            <p className="text-sm text-muted-foreground mt-2">
              Sign in with your Google account to continue
            </p>
          </div>

          <div className="flex flex-col items-center gap-3">
            {loading ? (
              <p className="text-sm text-muted-foreground">Signing in…</p>
            ) : (
              <GoogleLogin
                onSuccess={handleSuccess}
                onError={() => setError("Google sign-in failed. Please try again.")}
                useOneTap={false}
                theme="outline"
                size="large"
                width="320"
              />
            )}
            {error && (
              <p className="text-destructive text-sm text-center">{error}</p>
            )}
          </div>

          <p className="text-center text-xs text-muted-foreground">
            Accounts are provisioned by your administrator.
          </p>
        </div>
      </div>
    </GoogleOAuthProvider>
  );
}
