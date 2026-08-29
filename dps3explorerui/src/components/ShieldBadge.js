import { Shield } from "lucide-react";

export default function ShieldBadge({ hasCustomPermissions = false }) {
  if (!hasCustomPermissions) return null;
  return <Shield className="h-4 w-4 text-status-warning" aria-label="Custom permissions" title="Custom permissions" />;
}