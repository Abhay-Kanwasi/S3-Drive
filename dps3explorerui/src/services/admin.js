const API_HOSTNAME = process.env.NEXT_PUBLIC_HOSTNAME;
const adminHostname = `${API_HOSTNAME}/explorer/admin`;

function getAuthHeaders() {
  const token = localStorage.getItem("authToken");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

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

export const getAdminMe = async () => {
  const response = await fetch(`${adminHostname}/me`, {
    headers: getAuthHeaders(),
  });
  await throwIfNotOk(response, "Failed to fetch admin profile");
  return response.json();
};

export const getOnboardedOrgs = async () => {
  const response = await fetch(`${adminHostname}/orgs`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch orgs");
  return response.json();
};

export const getAvailableBuckets = async () => {
  const response = await fetch(`${adminHostname}/available-buckets`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch buckets");
  return response.json();
};

export const getAvailableSubscribers = async () => {
  const response = await fetch(`${adminHostname}/subscribers`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch subscribers");
  return response.json();
};

export const onboardOrg = async ({ subscription_id, bucket_name }) => {
  const response = await fetch(`${adminHostname}/orgs/onboard`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ subscription_id, bucket_name }),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || "Onboarding failed");
  }
  return response.json();
};

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
