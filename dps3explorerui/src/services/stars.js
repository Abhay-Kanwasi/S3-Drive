import { getAuthHeaders } from "@/services/auth";

const API_HOSTNAME = process.env.NEXT_PUBLIC_HOSTNAME;
const starsBase = `${API_HOSTNAME}/explorer/stars`;

function throwHttpError(response, fallback) {
  const error = new Error(fallback);
  error.status = response.status;
  return error;
}

export const listStars = async (orgId) => {
  const response = await fetch(`${starsBase}?org_id=${encodeURIComponent(orgId)}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const error = throwHttpError(response, err.detail || "Failed to load starred items");
    error.message = err.detail || error.message;
    throw error;
  }
  return response.json();
};

export const starItem = async ({ orgId, key, type, name, size, last_modified }) => {
  const response = await fetch(starsBase, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify({ org_id: orgId, key, type, name, size, last_modified }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const error = throwHttpError(response, err.detail || "Failed to star item");
    error.message = typeof err.detail === "string" ? err.detail : error.message;
    throw error;
  }
  return response.json();
};

export const unstarItem = async ({ orgId, key }) => {
  const params = new URLSearchParams({ org_id: String(orgId), key });
  const response = await fetch(`${starsBase}?${params.toString()}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const error = throwHttpError(response, err.detail || "Failed to unstar item");
    error.message = typeof err.detail === "string" ? err.detail : error.message;
    throw error;
  }
  return response.json();
};
