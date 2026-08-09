import { getAuthHeaders } from "@/services/auth";

const API_HOSTNAME = process.env.NEXT_PUBLIC_HOSTNAME;
const adminHostname = `${API_HOSTNAME}/explorer/admin`;

function apiErrorMessage(body, fallback) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msg = detail
      .map((d) => d.msg || d.message || "")
      .filter(Boolean)
      .join("; ");
    if (msg) return msg;
  }
  return fallback;
}

async function throwIfNotOk(response, fallback) {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const err = new Error(apiErrorMessage(body, fallback));
    err.status = response.status;
    throw err;
  }
}

/** Normalize org rows: subscription_id is a compat alias for org_key. */
function normalizeOrg(org) {
  if (!org) return org;
  const org_key = org.org_key || org.subscription_id || "";
  return {
    ...org,
    org_key,
    subscription_id: org.subscription_id || org_key,
    org_name: org.org_name || org.name || "",
  };
}

export const getAdminMe = async () => {
  const response = await fetch(`${adminHostname}/me`, {
    headers: getAuthHeaders(),
  });
  await throwIfNotOk(response, "Failed to fetch admin profile");
  const data = await response.json();
  if (data?.org) data.org = normalizeOrg(data.org);
  return data;
};

/** Owned organizations (onboarded). Falls back to legacy /admin/orgs path. */
export const getOrganizations = async () => {
  let response = await fetch(`${adminHostname}/organizations`, {
    headers: getAuthHeaders(),
  });
  if (response.status === 404) {
    response = await fetch(`${adminHostname}/orgs`, {
      headers: getAuthHeaders(),
    });
  }
  if (!response.ok) throw new Error("Failed to fetch organizations");
  const data = await response.json();
  return Array.isArray(data) ? data.map(normalizeOrg) : data;
};

/** @deprecated alias — use getOrganizations */
export const getOnboardedOrgs = getOrganizations;

export const getAvailableBuckets = async () => {
  const response = await fetch(`${adminHostname}/available-buckets`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch buckets");
  return response.json();
};

/**
 * Create / onboard an organization by binding an S3 bucket.
 * Accepts org_key, org_name, bucket_name (subscription_id accepted as alias for org_key).
 */
export const createOrganization = async ({
  org_key,
  org_name,
  bucket_name,
  subscription_id,
}) => {
  const key = org_key || subscription_id;
  const body = {
    org_key: key,
    org_name,
    bucket_name,
    // compat for APIs that still expect subscription_id
    subscription_id: key,
  };
  let response = await fetch(`${adminHostname}/organizations`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(body),
  });
  if (response.status === 404) {
    response = await fetch(`${adminHostname}/orgs/onboard`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({
        org_key: key,
        org_name,
        bucket_name,
        subscription_id: key,
      }),
    });
  }
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(apiErrorMessage(err, "Onboarding failed"));
  }
  return normalizeOrg(await response.json());
};

/** @deprecated alias — use createOrganization */
export const onboardOrg = createOrganization;

// ─── User Management ─────────────────────────────────────────────────────

export const getAdminUsers = async ({ q = "", orgId, page = 1, pageSize = 50 } = {}) => {
  const params = new URLSearchParams({
    q,
    page: String(page),
    page_size: String(pageSize),
  });
  if (orgId) params.set("org_id", String(orgId));
  const response = await fetch(`${adminHostname}/users?${params}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch users");
  return response.json();
};

export const getAdminUserDetail = async (userId) => {
  const response = await fetch(`${adminHostname}/users/${userId}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch user detail");
  return response.json();
};

const ROLE_TO_ID = {
  admin: 1,
  user: 2,
  master_admin: 3,
  super_admin: 4,
};

function normalizeRolePayload(role) {
  if (role == null) return role;
  if (typeof role === "number") return role;
  if (/^\d+$/.test(String(role))) return Number(role);
  return ROLE_TO_ID[role] ?? role;
}

export const createAdminUser = async ({
  username,
  email,
  role,
  organization_id,
  active = true,
}) => {
  const response = await fetch(`${adminHostname}/users`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({
      username,
      email,
      role: normalizeRolePayload(role),
      organization_id: organization_id ?? null,
      active,
    }),
  });
  await throwIfNotOk(response, "Failed to create user");
  return response.json();
};

export const updateAdminUser = async (userId, patch) => {
  const body = { ...patch };
  if (body.role != null) body.role = normalizeRolePayload(body.role);
  const response = await fetch(`${adminHostname}/users/${userId}`, {
    method: "PATCH",
    headers: getAuthHeaders(),
    body: JSON.stringify(body),
  });
  await throwIfNotOk(response, "Failed to update user");
  return response.json();
};

export const deactivateAdminUser = async (userId) => {
  const response = await fetch(`${adminHostname}/users/${userId}/deactivate`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to deactivate user");
  }
  return response.json();
};

export const reactivateAdminUser = async (userId) => {
  const response = await fetch(`${adminHostname}/users/${userId}/reactivate`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to reactivate user");
  }
  return response.json();
};

export const deactivateAccount = async (userId) => {
  const response = await fetch(`${adminHostname}/users/${userId}/account/deactivate`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  await throwIfNotOk(response, "Failed to deactivate account");
  return response.json();
};

export const reactivateAccount = async (userId) => {
  const response = await fetch(`${adminHostname}/users/${userId}/account/reactivate`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  await throwIfNotOk(response, "Failed to reactivate account");
  return response.json();
};

export const getAdminUserStats = async (orgId) => {
  const params = new URLSearchParams();
  if (orgId) params.set("org_id", String(orgId));
  const response = await fetch(`${adminHostname}/users/stats?${params}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch user stats");
  return response.json();
};

export const exportUsersCSV = async ({ q = "", orgId } = {}) => {
  const params = new URLSearchParams({ q });
  if (orgId) params.set("org_id", String(orgId));
  const response = await fetch(`${adminHostname}/users/export?${params}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to export users");
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "users_export.csv";
  a.click();
  window.URL.revokeObjectURL(url);
};

// ─── Audit Log ───────────────────────────────────────────────────────────

export const getAuditEvents = async ({ orgId, userId, eventType, dateFrom, dateTo, offset = 0, pageSize = 20 } = {}) => {
  const params = new URLSearchParams({ offset: String(offset), page_size: String(pageSize) });
  if (orgId) params.set("org_id", String(orgId));
  if (userId) params.set("user_id", String(userId));
  if (eventType) params.set("event_type", eventType);
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const response = await fetch(`${adminHostname}/audit?${params}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch audit events");
  return response.json();
};

export const exportAuditCSV = async ({ orgId, userId, eventType, dateFrom, dateTo } = {}) => {
  const params = new URLSearchParams();
  if (orgId) params.set("org_id", String(orgId));
  if (userId) params.set("user_id", String(userId));
  if (eventType) params.set("event_type", eventType);
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const response = await fetch(`${adminHostname}/audit/export?${params}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to export audit log");
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "audit_log.csv";
  a.click();
  window.URL.revokeObjectURL(url);
};

// ─── Group Management ────────────────────────────────────────────────────

export const getGroups = async (orgId) => {
  const response = await fetch(`${adminHostname}/groups?org_id=${orgId}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch groups");
  return response.json();
};

export const getGroupDetail = async (groupId) => {
  const response = await fetch(`${adminHostname}/groups/${groupId}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch group");
  return response.json();
};

export const createGroup = async ({ org_id, name, member_user_ids = [] }) => {
  const response = await fetch(`${adminHostname}/groups`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ org_id, name, member_user_ids }),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || "Failed to create group");
  }
  return response.json();
};

export const renameGroup = async (groupId, name) => {
  const response = await fetch(`${adminHostname}/groups/${groupId}`, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || "Failed to rename group");
  }
  return response.json();
};

export const getOtpApprovers = async (orgId) => {
  const params = new URLSearchParams({ org_id: String(orgId) });
  const response = await fetch(`${adminHostname}/otp/approvers?${params}`, {
    headers: getAuthHeaders(),
  });
  await throwIfNotOk(response, "Failed to load OTP approvers");
  return response.json();
};

export const sendOtp = async ({ purpose = "sensitive_action", recipient_user_id } = {}) => {
  const body = { purpose };
  if (recipient_user_id != null) body.recipient_user_id = recipient_user_id;
  const response = await fetch(`${adminHostname}/otp/send`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(body),
  });
  await throwIfNotOk(response, "Failed to send approval email");
  return response.json();
};

export const deleteGroup = async (groupId) => {
  const response = await fetch(`${adminHostname}/groups/${groupId}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(apiErrorMessage(err, "Failed to delete group"));
  }
  return response.json();
};

// ─── Members ─────────────────────────────────────────────────────────────

export const addMembers = async (groupId, userIds) => {
  const response = await fetch(`${adminHostname}/groups/${groupId}/members`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ user_ids: userIds }),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || "Failed to add members");
  }
  return response.json();
};

export const removeMember = async (groupId, userId) => {
  const response = await fetch(
    `${adminHostname}/groups/${groupId}/members/${userId}`,
    { method: "DELETE", headers: getAuthHeaders() },
  );
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || "Failed to remove member");
  }
  return response.json();
};

// ─── Folder Grants ───────────────────────────────────────────────────────

export const getGrants = async (groupId) => {
  const response = await fetch(`${adminHostname}/groups/${groupId}/grants`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch grants");
  return response.json();
};

export const createGrant = async (groupId, { prefix, access_level }) => {
  const response = await fetch(`${adminHostname}/groups/${groupId}/grants`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ prefix, access_level }),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || "Failed to create grant");
  }
  return response.json();
};

export const removeGrant = async (groupId, grantId) => {
  const response = await fetch(
    `${adminHostname}/groups/${groupId}/grants/${grantId}`,
    { method: "DELETE", headers: getAuthHeaders() },
  );
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || "Failed to remove grant");
  }
  return response.json();
};

// ─── Org User Search & Folder Tree ───────────────────────────────────────

export const searchOrgUsers = async (orgId, search = "", page = 1, pageSize = 50) => {
  const params = new URLSearchParams({ search, page: String(page), page_size: String(pageSize) });
  const response = await fetch(
    `${adminHostname}/orgs/${orgId}/users?${params}`,
    { headers: getAuthHeaders() },
  );
  if (!response.ok) throw new Error("Failed to search users");
  return response.json();
};

export const getFolderTree = async (orgId, prefix = "") => {
  const params = new URLSearchParams({ prefix });
  const response = await fetch(
    `${adminHostname}/orgs/${orgId}/folder-tree?${params}`,
    { headers: getAuthHeaders() },
  );
  if (!response.ok) throw new Error("Failed to fetch folders");
  return response.json();
};

// ─── Platform Settings ──────────────────────────────────────────────────

export const getPlatformSettings = async () => {
  const response = await fetch(`${adminHostname}/settings`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch platform settings");
  return response.json();
};

export const updatePlatformSettings = async ({ allowed_extensions, max_upload_bytes }) => {
  const body = {};
  if (allowed_extensions !== undefined) body.allowed_extensions = allowed_extensions;
  if (max_upload_bytes !== undefined) body.max_upload_bytes = max_upload_bytes;
  const response = await fetch(`${adminHostname}/settings`, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || "Failed to update settings");
  }
  return response.json();
};

// ─── Un-onboard (4-eyes) ─────────────────────────────────────────────────

export const getUnonboardApprovers = async () => {
  const response = await fetch(`${adminHostname}/unonboard/approvers`, {
    headers: getAuthHeaders(),
  });
  await throwIfNotOk(response, "Failed to load approvers");
  return response.json();
};

export const sendUnonboardOtp = async (orgId) => {
  const response = await fetch(`${adminHostname}/orgs/${orgId}/unonboard/send-otp`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  await throwIfNotOk(response, "Failed to send OTP");
  return response.json();
};

export const submitUnonboardRequest = async (orgId, { approver_user_id, otp_code }) => {
  const response = await fetch(`${adminHostname}/orgs/${orgId}/unonboard/request`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ approver_user_id, otp_code }),
  });
  await throwIfNotOk(response, "Failed to submit un-onboard request");
  return response.json();
};

// ─── Email approvals (group delete + un-onboard) ────────────────────────

export const getApprovalReview = async ({ id, token, action }) => {
  const params = new URLSearchParams({ id: String(id), token, action });
  const response = await fetch(`${adminHostname}/approval/review?${params}`, {
    headers: getAuthHeaders(),
  });
  await throwIfNotOk(response, "Failed to load approval");
  return response.json();
};

export const submitApprovalDecision = async ({ id, token, action }) => {
  const response = await fetch(`${adminHostname}/approval/respond`, {
    method: "POST",
    headers: { ...getAuthHeaders(), Accept: "application/json" },
    body: JSON.stringify({ id, token, action }),
  });
  await throwIfNotOk(response, "Failed to submit approval");
  return response.json();
};
