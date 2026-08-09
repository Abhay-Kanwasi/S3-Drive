import { getAuthHeaders } from "@/services/auth";

const API_HOSTNAME = process.env.NEXT_PUBLIC_HOSTNAME;
const browseHostname = `${API_HOSTNAME}/explorer/browse`;

/** Access status for current user (does not 403 on S3 deactivation). */
export const getExplorerAccess = async () => {
  const response = await fetch(`${browseHostname}/me`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const error = new Error(err.detail || "Failed to check access");
    error.status = response.status;
    throw error;
  }
  return response.json();
};

export function isS3ExplorerDeactivated(access) {
  return access?.block_reason === "s3_explorer" || access?.s3_deactivated === true;
}

export function isAccountInactive(access) {
  return (
    access?.block_reason === "account" ||
    access?.block_reason === "uam" ||
    access?.account_active === false ||
    access?.uam_active === false
  );
}
