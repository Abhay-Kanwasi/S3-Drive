"use client";
import { useQuery, useMutation, useQueryClient } from "react-query";
import FileCard from "./FileCard";
import FileRow from "./FileRow";
import { loadContents, loadFolderitems } from "@/services/Queries";
import { listStars, starItem, unstarItem } from "@/services/stars";
import { useContext, useEffect, useMemo, useState } from "react";
import { ApplicationContext } from "@/services/ContextProvider";
import { getUploadConstraints } from "@/services/server";
import { getRecentFiles, removeRecentFile } from "@/services/localStorage";
import ContextMenu from "./context";
import { X } from "lucide-react";

export default function View({ children }) {
  const {
    userid,
    path,
    card,
    setPath,
    setKeys,
    setDuplicates,
    trashpath,
    trashView,
    starredView,
    setStarredView,
    recentView,
    setRecentView,
    basePath,
    currentOrg,
    setContexterror,
    setContexterrormodal,
    setViewerFile,
    viewerFile,
  } = useContext(ApplicationContext);

  const queryClient = useQueryClient();
  const [contextMenuState, setContextMenuState] = useState({ visible: false, x: 0, y: 0, item: null });
  const [mutatingKey, setMutatingKey] = useState(null);
  const orgId = currentOrg?.id;
  const starsQueryKey = ["stars", userid, orgId];

  const { data: constraints } = useQuery("upload-constraints", getUploadConstraints, { staleTime: 5 * 60 * 1000 });
  const colorMap = {};
  if (constraints?.extension_colors) {
    for (const entry of constraints.extension_colors) colorMap[entry.ext] = entry.color;
  }

  const contents = useQuery(
    ["contents", path, orgId],
    () => loadContents(path, basePath, orgId),
    { cacheTime: 3000, enabled: Boolean(orgId) && !trashView && !starredView && !recentView }
  );
  const trashItems = useQuery(
    ["trash", trashpath, orgId],
    () => loadFolderitems(orgId),
    { cacheTime: 3000, enabled: Boolean(orgId) && trashView }
  );
  const starsQuery = useQuery(
    starsQueryKey,
    () => listStars(orgId),
    {
      enabled: Boolean(userid && orgId),
      staleTime: 60 * 1000,
      keepPreviousData: true,
      retry: false,
    }
  );

  // Get recent files from localStorage.
  // Re-reads when recentView activates OR when the file viewer closes (viewerFile → null).
  const [recentFiles, setRecentFilesState] = useState([]);
  useEffect(() => {
    if (!recentView || !orgId) {
      setRecentFilesState([]);
      return;
    }
    const allRecent = getRecentFiles();
    setRecentFilesState(
      allRecent
        .filter(f => String(f.orgId) === String(orgId))
        .map(f => ({
          name: f.name,
          key: f.key,
          type: f.type || "file",
          size: f.size || "--",
          last_modified: f.last_modified || new Date(f.timestamp).toLocaleString(),
          accessible: true,
        }))
    );
  // viewerFile dep: re-read list when modal closes so newly tracked files appear
  }, [recentView, orgId, viewerFile]);

  const starSet = useMemo(() => {
    const items = starsQuery.data?.items || [];
    return new Set(items.map((i) => i.key));
  }, [starsQuery.data]);
  const starsReady = starsQuery.isSuccess;

  useEffect(() => {
    if (contents.data) {
      const _names = [];
      for (let _d of contents.data) _names.push(_d.name);
      setDuplicates(new Set(_names));
    }
  }, [contents.data, setDuplicates]);

  const handleOpen = (item) => {
    if (item.accessible === false) return;
    if (item.type === "folder") {
      setStarredView(false);
      setRecentView(false);
      setPath(item.key || item.keypath);
      const _k = (item.key || item.keypath).split("/");
      setKeys(_k.splice(0, _k.length - 1));
    } else if (item.type === "file" && recentView) {
      // Open file viewer for recent files
      setViewerFile({ fileKey: item.key, fileName: item.name });
    }
  };

  const handleContextMenu = (e, item) => {
    setContextMenuState({ visible: true, x: e.pageX, y: e.pageY, item });
  };

  const starMutation = useMutation(
    ({ starred, item }) => {
      const key = item.key || item.keypath;
      if (starred) {
        return unstarItem({ orgId, key });
      }
      return starItem({
        orgId,
        key,
        type: item.type,
        name: item.name,
        size: item.size,
        last_modified: item.last_modified,
      });
    },
    {
      onMutate: ({ item }) => {
        setMutatingKey(item.key || item.keypath);
      },
      onSuccess: () => {
        queryClient.invalidateQueries(starsQueryKey);
      },
      onError: (err) => {
        if (err?.status === 404) {
          queryClient.invalidateQueries(starsQueryKey);
          return;
        }
        setContexterrormodal(true);
        setContexterror(err?.message || "Could not update star");
      },
      onSettled: () => setMutatingKey(null),
    }
  );

  const handleStarToggle = (item) => {
    if (!orgId || mutatingKey) return;
    const key = item.key || item.keypath;
    starMutation.mutate({ starred: starSet.has(key), item });
  };

  const activeData = starredView
    ? (starsQuery.isSuccess ? (starsQuery.data?.items || []) : [])
    : recentView
      ? recentFiles
      : trashView
        ? (trashItems.isSuccess ? trashItems.data : [])
        : (contents.isSuccess ? contents.data : []);

  const isLoading = starredView
    ? starsQuery.isLoading
    : recentView
      ? false
      : trashView
        ? trashItems.isLoading
        : contents.isLoading;

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

  if (starredView && !isLoading && activeData.length === 0) {
    return (
      <p className="text-sm text-muted-foreground mt-8 w-full text-center">
        No starred items yet. Star a file or folder to see it here.
      </p>
    );
  }

  if (recentView && !isLoading && activeData.length === 0) {
    return (
      <p className="text-sm text-muted-foreground mt-8 w-full text-center">
        No recent files yet. Open a file to see it here.
      </p>
    );
  }

  const handleRemoveRecent = (key) => {
    removeRecentFile(key);
    setRecentFilesState((prev) => prev.filter((f) => f.key !== key));
  };

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
          accessible: data.accessible !== false,
        };
        const isStarred = starsReady && starSet.has(itemObj.key);
        const tileProps = {
          item: itemObj,
          onOpen: handleOpen,
          // In recent view, single-click on a file opens the viewer directly
          onSelect: (recentView && itemObj.type === "file")
            ? () => setViewerFile({ fileKey: itemObj.key, fileName: itemObj.name })
            : () => {},
          onContextMenu: handleContextMenu,
          colorMap,
          starred: isStarred,
          onStarToggle: handleStarToggle,
          starDisabled: mutatingKey === itemObj.key,
          starsReady,
          accessible: itemObj.accessible,
        };

        const tile = card ? (
          <FileCard key={itemObj.key || index} {...tileProps} />
        ) : (
          <FileRow key={itemObj.key || index} {...tileProps} />
        );

        if (recentView) {
          return (
            <div key={itemObj.key || index} className="relative group">
              {tile}
              <button
                type="button"
                title="Remove from Recent"
                onClick={(e) => { e.stopPropagation(); handleRemoveRecent(itemObj.key); }}
                className={`absolute ${card ? "top-1 right-1" : "top-1/2 -translate-y-1/2 right-2"} p-1 rounded-full bg-white border border-border text-muted-foreground hover:text-red-500 hover:border-red-300 shadow-sm opacity-0 group-hover:opacity-100 transition-opacity z-10`}
              >
                <X className="w-3 h-3" strokeWidth={2.5} />
              </button>
            </div>
          );
        }

        return tile;
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
