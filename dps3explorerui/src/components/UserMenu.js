"use client";

import { ChevronDown, UserCircle } from "lucide-react";

export default function UserMenu({ user = {}, onOpen }) {
  const initials = (user.name || user.email || "U").slice(0, 1).toUpperCase();

  return (
    <button
      type="button"
      onClick={onOpen}
      className="inline-flex max-w-52 items-center gap-2 rounded-lg p-1.5 text-left hover:bg-gray-100"
      aria-label="Open user menu"
    >
      {user.avatarUrl ? (
        <img src={user.avatarUrl} alt="" className="h-8 w-8 rounded-full object-cover" />
      ) : (
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-subtle text-sm font-semibold text-accent">
          {initials}
        </span>
      )}
      <span className="hidden min-w-0 sm:block">
        <span className="block truncate text-sm font-semibold text-foreground">{user.name || "User"}</span>
        <span className="block truncate text-xs text-muted-foreground">{user.email || ""}</span>
      </span>
      <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
      <UserCircle className="sr-only" aria-hidden="true" />
    </button>
  );
}