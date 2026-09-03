"use client";

import { useRouter } from "next/navigation";
import SearchBar from "@/components/SearchBar";
import NotificationBell from "@/components/NotificationBell";
import UserMenu from "@/components/UserMenu";

export default function TopBar({ user, onSearch, hideSearch = false, onOpenNotifications }) {
  const router = useRouter();
  const openNotifRef = typeof onOpenNotifications === "object" ? onOpenNotifications : null;
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={() => router.push("/")}
          className="flex items-center gap-2 hover:opacity-80 transition-opacity"
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-subtle text-sm font-bold text-accent">
            SD
          </div>
          <span className="text-base font-semibold text-foreground">S3 Drive</span>
        </button>

        {!hideSearch && (
          <div className="hidden min-w-0 flex-1 md:block">
            <SearchBar onSearch={onSearch} scope="global" disabled />
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          <NotificationBell onOpenRequest={openNotifRef} />
          <UserMenu user={user} />
        </div>
      </div>
    </header>
  );
}
