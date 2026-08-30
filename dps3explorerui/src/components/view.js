"use client";
import { useQuery } from "react-query";
import FileCard from "./FileCard";
import FileRow from "./FileRow";
import { loadContents, loadFolderitems } from "@/services/Queries";
import { useContext, useEffect, useState } from "react";
import { ApplicationContext } from "@/services/ContextProvider";
import { getUploadConstraints } from "@/services/server";
import ContextMenu from "./context";

export default function View({ children }) {
  const {
    userid,
    path,
    card,
    setPath,
    setKeys,
    setDuplicates,
    duplicates,
    trashpath,
    trashView,
    basePath,
    currentOrg,
    isAdmin,
    setViewerFile,
    setContextname,
    setContextsize,
    setContextlastmod,
    setContextdelete,
    setContextinfo,
    setContextextension,
    setContextauthor,
    setContexterror,
    setContexterrormodal,
  } = useContext(ApplicationContext);

  const [contextMenuState, setContextMenuState] = useState({ visible: false, x: 0, y: 0, item: null });
  // BACKEND REQUIRED: GET /api/items/:id/star — star persistence not yet available
  const [starredKeys, setStarredKeys] = useState(() => {
    try { return new Set(JSON.parse(localStorage.getItem("starredKeys") || "[]")); } catch { return new Set(); }
  });

  const { data: constraints } = useQuery("upload-constraints", getUploadConstraints, { staleTime: 5 * 60 * 1000 });
  const colorMap = {};
  if (constraints?.extension_colors) {
    for (const entry of constraints.extension_colors) colorMap[entry.ext] = entry.color;
  }

  const contents = useQuery(
    ["contents", path, currentOrg?.id],
    () => loadContents(path, basePath, currentOrg?.id),
    { cacheTime: 3000 }
  );
  const trashItems = useQuery(
    ["trash", trashpath, currentOrg?.id],
    () => loadFolderitems(currentOrg?.id),
    { cacheTime: 3000 }
  );

  useEffect(() => {
    if (contents.data) {
      const _names = [];
      for (let _d of contents.data) _names.push(_d.name);
      setDuplicates(new Set(_names));
    }
  }, [contents.data]);

  const handleOpen = (item) => {
    if (item.type === "folder") {
      setPath(item.key || item.keypath);
      const _k = (item.key || item.keypath).split("/");
      setKeys(_k.splice(0, _k.length - 1));
    }
  };

  const handleContextMenu = (e, item) => {
    setContextMenuState({ visible: true, x: e.pageX, y: e.pageY, item });
  };

  const handleStarToggle = (item) => {
    const key = item.key || item.keypath;
    setStarredKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      try { localStorage.setItem("starredKeys", JSON.stringify([...next])); } catch {}
      return next;
    });
    // BACKEND REQUIRED: PATCH /api/items/:id/star — persist star state server-side
  };

  const activeData = trashView
    ? (trashItems.isSuccess ? trashItems.data : [])
    : (contents.isSuccess ? contents.data : []);

  const isLoading = trashView ? trashItems.isLoading : contents.isLoading;

  if (isLoading) {
    return (
      <div className="flex flex-wrap animate-pulse">
        <div className="flex flex-row justify-center items-center w-40 h-40 mr-6 mt-4 mb-4 bg-gray-300 select-none cursor-pointer border rounded-lg px-6 py-4">
          <span className="text-gray-400">Loading...</span>
        </div>
      </div>
    );
  }

  const contextItem = contextMenuState.item;

  return (
    <>
      {activeData.map((data, index) => {
        const itemObj = {
          name: data.name,
          type: data.type,
          size: data.size,
          last_modified: data.last_modified,
          key: data.trash_key || data.key || data.keypath,
          created_by_role: data.created_by_role,
          is_own: data.is_own,
        };
        const isStarred = starredKeys.has(itemObj.key);
        return card ? (
          <FileCard
            key={index}
            item={itemObj}
            onOpen={handleOpen}
            onSelect={() => {}}
            onContextMenu={handleContextMenu}
            colorMap={colorMap}
            starred={isStarred}
            onStarToggle={handleStarToggle}
          />
        ) : (
          <FileRow
            key={index}
            item={itemObj}
            onOpen={handleOpen}
            onSelect={() => {}}
            onContextMenu={handleContextMenu}
            colorMap={colorMap}
            starred={isStarred}
            onStarToggle={handleStarToggle}
          />
        );
      })}

      {contextMenuState.visible && contextItem && (
        <ContextMenu
          top={contextMenuState.y}
          left={contextMenuState.x}
          visible={contextMenuState.visible}
          name={contextItem.name}
          size={contextItem.size}
          last_modified={contextItem.last_modified}
          setVisible={(v) => setContextMenuState((s) => ({ ...s, visible: typeof v === "function" ? v(s.visible) : v }))}
          itemType={contextItem.type}
          keypath={contextItem.key}
          created_by_role={contextItem.created_by_role}
          is_own={contextItem.is_own}
        />
      )}
    </>
  );
}
