"use client";

import { File, Folder, Star } from "lucide-react";
import ShieldBadge from "./ShieldBadge";
import { FileSpreadsheet, FileJson, FileArchive, FileText, FileImage } from "lucide-react";
import Image from "next/image";
import FolderIcon from "../app/assets/folder.svg";

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
  return <IconComponent className="w-5 h-5 mr-2 flex-shrink-0" style={{ color }} strokeWidth={1.5} />;
}

export default function FileRow({ item, onOpen, onSelect, onContextMenu, colorMap, starred, onStarToggle, starDisabled, starsReady, accessible = true }) {
  const isFolder = item.type === "folder";
  const hasCustomPerms = Boolean(item.hasCustomPermissions || (item.created_by_role && item.created_by_role === "admin"));
  const inaccessible = accessible === false;
  const starLabel = starred ? "Unstar" : "Star";

  return (
    <div
      onDoubleClick={(e) => {
        if (inaccessible) return;
        if (isFolder) { e.preventDefault(); onOpen?.(item); }
      }}
      onContextMenu={(e) => { e.preventDefault(); onContextMenu?.(e, item); }}
      onClick={() => { if (!inaccessible) onSelect?.(item); }}
      className={`flex text-sm flex-row grow bg-card select-none cursor-pointer border border-border rounded-lg px-2 py-2 mr-10 mt-2 hover:bg-gray-50 w-full transition-colors duration-150 ${inaccessible ? "opacity-50" : ""}`}
    >
      <div className="w-2/3 text-foreground inline-flex overflow-hidden text-ellipsis items-center">
        {isFolder
          ? <Image width={25} className="mr-2" src={FolderIcon} alt="Folder" />
          : <FileTypeIcon filename={item.name} colorMap={colorMap} />}
        {item.name}
        {inaccessible && <span className="ml-2 text-xs text-muted-foreground">No longer accessible</span>}
        {hasCustomPerms && <span className="ml-2 inline-flex items-center"><ShieldBadge hasCustomPermissions /></span>}
      </div>
      <div className="w-20 text-muted-foreground">{isFolder ? "" : item.size || "--"}</div>
      <div className="w-40 text-muted-foreground">{item.last_modified || "--"}</div>
      {onStarToggle && (
        <button
          type="button"
          disabled={starDisabled}
          onClick={(e) => { e.stopPropagation(); onStarToggle(item); }}
          className={`ml-auto p-1 rounded hover:bg-gray-100 ${!starsReady ? "opacity-40" : ""} ${starDisabled ? "opacity-50 cursor-not-allowed" : ""}`}
          title={starLabel}
          aria-label={starLabel}
        >
          <Star className={`w-3.5 h-3.5 ${starred ? "fill-status-warning text-status-warning" : "text-muted-foreground"}`} strokeWidth={1.5} />
        </button>
      )}
    </div>
  );
}