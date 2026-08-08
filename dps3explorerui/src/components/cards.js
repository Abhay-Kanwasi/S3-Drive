"use client";
import { useMutation, useQuery } from "react-query";
import Image from "next/image";
import FolderIcon from "../app/assets/folder.svg";
import { loadContents } from "@/services/Queries";
import { useContext, useState } from "react";
import { ApplicationContext } from "@/services/ContextProvider";
import ContextMenu from "./context";
import { Shield, User, FileSpreadsheet, FileJson, FileArchive, FileText, FileImage, File } from "lucide-react";
import { getUploadConstraints } from "@/services/server";

const ICON_MAP = {
  csv: FileSpreadsheet,
  xlsx: FileSpreadsheet,
  xls: FileSpreadsheet,
  parquet: FileSpreadsheet,
  orc: FileSpreadsheet,
  json: FileJson,
  zip: FileArchive,
  gz: FileArchive,
  pdf: FileText,
  docx: FileText,
  txt: FileText,
  png: FileImage,
  jpg: FileImage,
  jpeg: FileImage,
  gif: FileImage,
};

function FileTypeIcon({ filename, colorMap }) {
  const ext = filename?.split(".").pop()?.toLowerCase() || "";
  const cls = "w-8 h-8";
  const IconComponent = ICON_MAP[ext] || File;
  const color = colorMap?.[`.${ext}`] || "#9ca3af";
  return <IconComponent className={cls} style={{ color }} strokeWidth={1.2} />;
}

export default function Cards({ name, type, size, last_modified, keypath, created_by_role, is_own }) {
  const { setPath, setKeys, userid, basePath, currentOrg } = useContext(ApplicationContext);
  const folderMutation = useMutation({
    mutationFn: ({ keypath, basePath }) =>
      loadContents(keypath, basePath, currentOrg?.id),
  });

  const { data: constraints } = useQuery("upload-constraints", getUploadConstraints, {
    staleTime: 5 * 60 * 1000,
  });
  const colorMap = {};
  if (constraints?.extension_colors) {
    for (const entry of constraints.extension_colors) {
      colorMap[entry.ext] = entry.color;
    }
  }

  var [visible, setVisible] = useState(false);
  var [location, setLocation] = useState({
    x: 0,
    y: 0,
  });
  return (
    <div
      className="mt-4 mr-6 text-foreground"
      onDoubleClick={(e) => {
        if (type === "folder") {
          e.preventDefault();
          setPath(keypath);
          const _k = keypath.split("/");
          const _keys = _k.splice(0, _k.length - 1);
          setKeys(_keys);
          folderMutation.mutate({ keypath, basePath });
        }
      }}
      onContextMenu={(e) => {
        e.preventDefault();
        setLocation({ x: e.pageX, y: e.pageY });
        setVisible((visible = !visible));
      }}
    >
      <div className="flex flex-col items-center bg-card select-none cursor-pointer border border-border w-40 rounded-lg px-6 py-4 card-shadow hover-button relative">
        {type === "folder" && created_by_role && (
          <span className="absolute top-2 right-2">
            {created_by_role === "admin" ? (
              <Shield className="w-3.5 h-3.5 text-amber-500" />
            ) : (
              <User className="w-3.5 h-3.5 text-blue-400" />
            )}
          </span>
        )}
        <div className="h-14 flex items-center justify-center">
          {type === "file" ? (
            <FileTypeIcon filename={name} colorMap={colorMap} />
          ) : (
            <Image width={32} height={32} src={FolderIcon} alt="Folder" />
          )}
        </div>
        <p className="truncate w-32 text-center hover:text-clip text-sm">
          {name}
        </p>
        <p className="text-center text-sm text-muted-foreground">
          {type === "file" ? size : "Folder"}
        </p>
      </div>
      <ContextMenu
        top={location.y}
        left={location.x}
        visible={visible}
        name={name}
        size={size}
        last_modified={last_modified}
        setVisible={setVisible}
        itemType={type}
        keypath={keypath}
        created_by_role={created_by_role}
        is_own={is_own}
      />
    </div>
  );
}
