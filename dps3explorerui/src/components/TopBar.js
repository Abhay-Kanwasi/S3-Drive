"use client";

import SearchBar from "@/components/SearchBar";
import NotificationBell from "@/components/NotificationBell";
import UserMenu from "@/components/UserMenu";

export default function TopBar({ user, onSearch, hideSearch = false }) {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-subtle text-sm font-bold text-accent">
            SD
          </div>
          <span className="text-base font-semibold text-foreground">S3 Drive</span>
        </div>

        {!hideSearch && (
          <div className="hidden min-w-0 flex-1 md:block">
            <SearchBar onSearch={onSearch} scope="global" disabled />
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          <NotificationBell />
          <UserMenu user={user} />
        </div>
      </div>
    </header>
  );
}
