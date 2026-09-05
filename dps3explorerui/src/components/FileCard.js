"use client";

import { File, Folder, Star } from "lucide-react";
import ShieldBadge from "./ShieldBadge";
import { FileSpreadsheet, FileJson, FileArchive, FileText, FileImage } from "lucide-react";
import FolderIcon from "./FolderIcon";

const ICON_MAP = {
  csv: FileSpreadsheet, xlsx: FileSpreadsheet, xls: FileSpreadsheet,
  parquet: FileSpreadsheet, orc: FileSpreadsheet,
  json: FileJson,
  zip: FileArchive, gz: FileArchive,
  pdf: FileText, docx: FileText, txt: FileText,
  png: FileImage, jpg: FileImage, jpeg: FileImage, gif: FileImage,
};

function FileTypeIcon({ filename, colorMap }) {
  const ext = filename?.split(".").pop()?.toLowerCase() || "";
  const IconComponent = ICON_MAP[ext] || File;
  const color = colorMap?.[`.${ext}`] || "#9ca3af";
  return <IconComponent className="w-8 h-8" style={{ color }} strokeWidth={1.2} />;
}

export default function FileCard({ item, onOpen, onSelect, onContextMenu, colorMap, starred, onStarToggle, starDisabled, starsReady, accessible = true }) {
  const isFolder = item.type === "folder";
  const hasCustomPerms = Boolean(item.hasCustomPermissions || (item.created_by_role && item.created_by_role === "admin"));
  const inaccessible = accessible === false;
  const starLabel = starred ? "Unstar" : "Star";

  return (
    <div
      className={`mt-4 mr-6 text-foreground relative ${inaccessible ? "opacity-50" : ""}`}
      onDoubleClick={(e) => {
        if (inaccessible) return;
        if (isFolder) { e.preventDefault(); onOpen?.(item); }
      }}
      onContextMenu={(e) => { e.preventDefault(); onContextMenu?.(e, item); }}
    >
      <div
        onClick={() => { if (!inaccessible) onSelect?.(item); }}
        className="flex flex-col items-center bg-card select-none cursor-pointer border border-border w-40 rounded-lg px-6 py-4 card-shadow hover-button relative"
      >
        {hasCustomPerms && (
          <span className="absolute top-2 right-2">
            <ShieldBadge hasCustomPermissions />
          </span>
        )}
        {onStarToggle && (
          <button
            type="button"
            disabled={starDisabled}
            onClick={(e) => { e.stopPropagation(); onStarToggle(item); }}
            className={`absolute top-2 left-2 p-0.5 rounded hover:bg-gray-100 ${!starsReady ? "opacity-40" : ""} ${starDisabled ? "opacity-50 cursor-not-allowed" : ""}`}
            title={starLabel}
            aria-label={starLabel}
          >
            <Star className={`w-3.5 h-3.5 ${starred ? "fill-status-warning text-status-warning" : "text-muted-foreground"}`} strokeWidth={1.5} />
          </button>
        )}
        <div className="h-14 flex items-center justify-center">
          {isFolder
            ? <FolderIcon className="w-9 h-9" />
            : <FileTypeIcon filename={item.name} colorMap={colorMap} />}
        </div>
        <p className="truncate w-32 text-center text-sm">{item.name}</p>
        <p className="text-center text-sm text-muted-foreground">
          {inaccessible ? "No longer accessible" : (isFolder ? "Folder" : item.size || "--")}
        </p>
      </div>
    </div>
  );
}