"use client";

import { useRouter } from "next/navigation";
import { ChevronDown, UserCircle, LogOut } from "lucide-react";
import { setSelectedUserId } from "@/services/auth";

export default function UserMenu({ user = {}, onOpen }) {
  const router = useRouter();
  const initials = (user.name || user.email || "U").slice(0, 1).toUpperCase();

  const handleLogout = () => {
    setSelectedUserId(null);
    router.replace("/login");
  };

  return (
    <div className="flex items-center gap-1">
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

      <button
        type="button"
        onClick={handleLogout}
        className="flex items-center justify-center h-8 w-8 rounded-lg text-muted-foreground hover:text-destructive hover:bg-gray-100 transition-colors"
        aria-label="Log out"
        title="Log out"
      >
        <LogOut className="h-4 w-4" strokeWidth={1.5} />
      </button>
    </div>
  );
}
