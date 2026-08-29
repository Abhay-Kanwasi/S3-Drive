"use client";

import { Search } from "lucide-react";

export default function SearchBar({ onSearch, scope = "org", disabled = false }) {
  return (
    <form
      className="relative min-w-0 flex-1"
      onSubmit={(event) => {
        event.preventDefault();
        onSearch?.(event.currentTarget.elements.search.value);
      }}
    >
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <input
        name="search"
        type="search"
        disabled={disabled}
        placeholder={scope === "global" ? "Search across organizations" : "Search this organization"}
        title={disabled ? "Search coming soon" : undefined}
        className="w-full rounded-lg border border-border bg-card py-2 pl-9 pr-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:bg-muted"
        aria-label={scope === "global" ? "Global search" : "Organization search"}
      />
      {/* BACKEND REQUIRED: GET /api/search?q=&orgId= is not available yet. */}
    </form>
  );
}