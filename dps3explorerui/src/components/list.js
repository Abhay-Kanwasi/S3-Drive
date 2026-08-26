"use client";
import Image from "next/image";
import FolderIcon from "../app/assets/folder.svg";
import { useContext, useState } from "react";
import { useMutation, useQuery } from "react-query";
import { ApplicationContext } from "@/services/ContextProvider";
import { loadContents } from "@/services/Queries";
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
  const cls = "w-5 h-5 mr-2 flex-shrink-0";
  const IconComponent = ICON_MAP[ext] || File;
  const color = colorMap?.[`.${ext}`] || "#9ca3af";
  return <IconComponent className={cls} style={{ color }} strokeWidth={1.5} />;
}

export default function List({ name, type, size, keypath, last_modified, created_by_role, is_own }) {
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
    <>
      <div
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
        className="flex text-sm flex-row grow bg-card select-none cursor-pointer border border-border rounded-lg px-2 py-2 mr-10 mt-2 hover:bg-gray-50 w-full transition-colors duration-150"
      >
        <div className="w-2/3 text-foreground inline-flex overflow-hidden text-ellipsis items-center">
          {type === "file" ? (
            <FileTypeIcon filename={name} colorMap={colorMap} />
          ) : (
            <Image width={25} className="mr-2" src={FolderIcon} alt="Folder" />
          )}
          {name}
          {type === "folder" && created_by_role && (
            <span className="ml-2 inline-flex items-center">
              {created_by_role === "admin" ? (
                <Shield className="w-3 h-3 text-status-warning" />
              ) : (
                <User className="w-3 h-3 text-blue-400" />
              )}
            </span>
          )}
        </div>
        {type === "file" ? (
          <div className="w-20 text-muted-foreground">{size}</div>
        ) : (
          <div className="w-20 text-muted-foreground hidden">{size}</div>
        )}

        <div className="w-40 text-muted-foreground">{last_modified}</div>
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
    </>
  );
}
