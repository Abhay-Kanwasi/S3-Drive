"use client";

import { File, Folder } from "lucide-react";
import ShieldBadge from "./ShieldBadge";

export default function FileRow({ item, onOpen, onSelect }) {
  const isFolder = item.type === "folder";
  return (
    <button
      type="button"
      onDoubleClick={() => onOpen?.(item)}
      onClick={() => onSelect?.(item)}
      className="grid w-full grid-cols-[minmax(0,1fr)_7rem_10rem] items-center gap-3 border-b border-border px-3 py-3 text-left text-sm hover:bg-gray-50"
    >
      <span className="flex min-w-0 items-center gap-2">
        {isFolder ? <Folder className="h-5 w-5 shrink-0 text-accent" /> : <File className="h-5 w-5 shrink-0 text-muted-foreground" />}
        <span className="truncate font-medium text-foreground">{item.name}</span>
        <ShieldBadge hasCustomPermissions={Boolean(item.hasCustomPermissions || item.created_by_role)} />
      </span>
      <span className="text-muted-foreground">{isFolder ? "Folder" : item.size || "--"}</span>
      <span className="truncate text-muted-foreground">{item.last_modified || "--"}</span>
    </button>
  );
}