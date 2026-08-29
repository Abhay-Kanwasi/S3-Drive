"use client";

import { File, Folder } from "lucide-react";
import ShieldBadge from "./ShieldBadge";

export default function FileCard({ item, onOpen, onSelect }) {
  const isFolder = item.type === "folder";
  return (
    <button
      type="button"
      onDoubleClick={() => onOpen?.(item)}
      onClick={() => onSelect?.(item)}
      className="flex min-h-32 flex-col items-center justify-center gap-2 rounded-lg border border-border bg-card p-4 text-center hover:border-accent hover:shadow-sm"
    >
      {isFolder ? <Folder className="h-9 w-9 text-accent" /> : <File className="h-9 w-9 text-muted-foreground" />}
      <span className="flex max-w-full items-center gap-1">
        <span className="max-w-32 truncate text-sm font-medium text-foreground">{item.name}</span>
        <ShieldBadge hasCustomPermissions={Boolean(item.hasCustomPermissions || item.created_by_role)} />
      </span>
      <span className="text-xs text-muted-foreground">{isFolder ? "Folder" : item.size || "--"}</span>
    </button>
  );
}