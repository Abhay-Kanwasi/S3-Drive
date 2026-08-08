const API_HOSTNAME = process.env.NEXT_PUBLIC_HOSTNAME;
const browseHostname = `${API_HOSTNAME}/explorer/browse`;

function getAuthHeaders() {
  const token = localStorage.getItem("authToken");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

/** Access status for current user (does not 403 on S3 deactivation). */
export const getExplorerAccess = async () => {
  const response = await fetch(`${browseHostname}/me`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to check access");
  }
  return response.json();
};

export function isS3ExplorerDeactivated(access) {
  return access?.block_reason === "s3_explorer" || access?.s3_deactivated === true;
}
