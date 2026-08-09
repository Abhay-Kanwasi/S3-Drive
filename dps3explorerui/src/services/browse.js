import { getAuthHeaders } from "@/services/auth";

const API_HOSTNAME = process.env.NEXT_PUBLIC_HOSTNAME;
const browseHostname = `${API_HOSTNAME}/explorer/browse`;

export const browseFolders = async (orgId, prefix = "") => {
  const response = await fetch(`${browseHostname}/browse`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ org_id: orgId, prefix }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to browse");
  }
  return response.json();
};

/** List orgs the current user can access (sidebar). */
export const listAccessibleOrgs = async () => {
  const response = await fetch(`${browseHostname}/orgs`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to list organizations");
  }
  return response.json();
};

export const createFolder = async (orgId, parentPrefix, name) => {
  const response = await fetch(`${browseHostname}/folders/create`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ org_id: orgId, parent_prefix: parentPrefix, name }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const detail = err.detail;
    const msg = Array.isArray(detail) ? detail.map((d) => d.msg || d.message || "").join("; ") : detail || "Failed to create folder";
    throw new Error(msg);
  }
  return response.json();
};

export const renameFolder = async (orgId, prefix, newName) => {
  const response = await fetch(`${browseHostname}/folders/rename`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ org_id: orgId, prefix, new_name: newName }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to rename folder");
  }
  return response.json();
};

export const deleteFolder = async (orgId, prefix) => {
  const response = await fetch(`${browseHostname}/folders/delete`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ org_id: orgId, prefix }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to move to trash");
  }
  return response.json();
};

export const listTrash = async (orgId) => {
  const response = await fetch(`${browseHostname}/trash`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ org_id: orgId, prefix: "" }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to load trash");
  }
  return response.json();
};

export const restoreFromTrash = async (orgId, trashKey) => {
  const response = await fetch(`${browseHostname}/trash/restore`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ org_id: orgId, trash_key: trashKey }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to restore");
  }
  return response.json();
};

export const purgeFromTrash = async (orgId, trashKey) => {
  const response = await fetch(`${browseHostname}/trash/purge`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ org_id: orgId, trash_key: trashKey }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to permanently delete");
  }
  return response.json();
};

// -------- File Operations --------

const filesHostname = `${API_HOSTNAME}/explorer/files`;

export const renameFile = async (orgId, fileKey, newName, basePath) => {
  const response = await fetch(`${filesHostname}/rename`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ org_id: orgId, file_key: fileKey, new_name: newName, basePath }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to rename file");
  }
  return response.json();
};

export const copyFile = async (orgId, fileKey, targetPrefix, basePath) => {
  const response = await fetch(`${filesHostname}/copy`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ org_id: orgId, file_key: fileKey, target_prefix: targetPrefix, basePath }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to copy file");
  }
  return response.json();
};

export const moveFile = async (orgId, fileKey, targetPrefix, basePath) => {
  const response = await fetch(`${filesHostname}/move`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ org_id: orgId, file_key: fileKey, target_prefix: targetPrefix, basePath }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to move file");
  }
  return response.json();
};
