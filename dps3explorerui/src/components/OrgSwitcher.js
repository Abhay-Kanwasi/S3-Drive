"use client";

import { Building2, Check, ChevronDown } from "lucide-react";

export default function OrgSwitcher({ orgs = [], activeOrgId, onSwitch }) {
  const activeOrg = orgs.find((org) => String(org.id) === String(activeOrgId));

  return (
    <label className="relative block">
      <span className="sr-only">Organization</span>
      <Building2 className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <select
        value={activeOrgId ?? ""}
        onChange={(event) => onSwitch?.(event.target.value)}
        className="w-full appearance-none rounded-lg border border-border bg-card py-2 pl-9 pr-9 text-sm font-medium text-foreground outline-none hover:bg-gray-50 focus:ring-2 focus:ring-ring"
        aria-label="Switch organization"
      >
        {!activeOrg && <option value="">Select organization</option>}
        {orgs.map((org) => (
          <option key={org.id} value={org.id}>
            {org.org_name || org.name}
            {org.role ? ` · ${org.role}` : ""}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      {activeOrg && <Check className="sr-only" aria-hidden="true" />}
      {/* BACKEND REQUIRED: GET /api/orgs must return every organization and the user's role. */}
    </label>
  );
}