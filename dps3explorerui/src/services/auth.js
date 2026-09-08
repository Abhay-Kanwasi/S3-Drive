/**
 * Cookie-session auth helpers.
 * Sessions are maintained via HttpOnly cookies set by the backend.
 * No identity data is stored in localStorage or sent as headers.
 */

const API_HOSTNAME = process.env.NEXT_PUBLIC_HOSTNAME;
const authBase = `${API_HOSTNAME}/explorer/auth`;
const CSRF_COOKIE = "s3exp_csrf";

function csrfToken() {
  if (typeof document === "undefined") return "";
  return document.cookie
    .split(";")
    .map((value) => value.trim())
    .find((value) => value.startsWith(`${CSRF_COOKIE}=`))
    ?.slice(CSRF_COOKIE.length + 1) || "";
}

/** Exchange a Google credential for session cookies. */
export async function googleLogin(credential) {
  const response = await fetch(`${authBase}/google`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ credential }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const error = new Error(err.detail || "Login failed");
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export async function getOnboardOrgs() {
  const response = await fetch(`${authBase}/orgs`, { credentials: "include" });
  if (!response.ok) throw new Error("Failed to load organizations");
  return response.json();
}

export async function submitOnboarding({ onboard_token, username, organization_id }) {
  const response = await fetch(`${authBase}/onboard`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ onboard_token, username, organization_id: organization_id || null }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const error = new Error(err.detail || "Onboarding failed");
    error.status = response.status;
    throw error;
  }
  return response.json();
}

/** Rotate the access token using the refresh cookie. */
export async function refreshSession() {
  const response = await fetch(`${authBase}/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": csrfToken() },
  });
  if (!response.ok) throw Object.assign(new Error("Session expired"), { status: response.status });
  return response.json();
}

/** Clear session cookies on the backend. */
export async function logout() {
  await fetch(`${authBase}/logout`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": csrfToken() },
  });
}

/** Fetch the current authenticated user from the session cookie. */
export async function getSessionUser() {
  const response = await fetch(`${authBase}/me`, {
    credentials: "include",
  });
  if (!response.ok) {
    const error = new Error("Not authenticated");
    error.status = response.status;
    throw error;
  }
  return response.json();
}

/**
 * Credentialed fetch — always sends cookies.
 * Drop-in replacement for plain fetch across all service modules.
 */
export function apiFetch(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const token = csrfToken();
    if (token) headers.set("X-CSRF-Token", token);
  }
  return fetch(url, { ...options, headers, credentials: "include" });
}

/** Standard JSON headers for credentialed API calls. */
export function credentialedHeaders(extraHeaders = {}) {
  return {
    "Content-Type": "application/json",
    ...extraHeaders,
  };
}

/** @deprecated Use credentialedHeaders — kept for call-site compat during migration. */
export const getAuthHeaders = credentialedHeaders;

/** @deprecated No-op — cookies are sent automatically. */
export function authHeaders(extraHeaders = {}) {
  return extraHeaders;
}
