/**
 * Temporary identity stand-in for standalone Explorer.
 * Selected user id is sent as X-User-Id (replace with real auth later).
 */

const STORAGE_KEY = "explorerUserId";

export function getSelectedUserId() {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw == null || String(raw).trim() === "") return null;
  const id = String(raw).trim();
  return /^\d+$/.test(id) ? id : null;
}

export function setSelectedUserId(userId) {
  if (typeof window === "undefined") return;
  const id = userId == null ? "" : String(userId).trim();
  if (!id) {
    localStorage.removeItem(STORAGE_KEY);
    return;
  }
  localStorage.setItem(STORAGE_KEY, id);
}

/** Build headers with X-User-Id when a user is selected. */
export function authHeaders(extraHeaders = {}) {
  const userId = getSelectedUserId();
  return {
    ...(userId ? { "X-User-Id": String(userId) } : {}),
    ...extraHeaders,
  };
}

/** Alias used by some API modules. */
export function getAuthHeaders(extraHeaders = {}) {
  return {
    "Content-Type": "application/json",
    ...authHeaders(extraHeaders),
  };
}
