import { useRef, useEffect, useContext, useState } from "react";
import Image from "next/image";
import { useQueryClient } from "react-query";
import Restore from "../app/assets/restore.svg";
import { ApplicationContext } from "@/services/ContextProvider";
import { restoreItems, isViewableFile } from "@/services/server";
import { renameFolder, restoreFromTrash, purgeFromTrash, renameFile, copyFile, moveFile } from "@/services/browse";
import { get_metadata } from "@/services/Queries";
import { Info, Trash2, Pencil, FolderX, Copy, Eye, FolderInput, FolderSymlink } from "lucide-react";
import FolderPickerModal from "./FolderPickerModal";

export default function ContextMenu({
  top,
  left,
  name,
  size,
  last_modified,
  visible,
  setVisible,
  itemType,
  keypath,
  created_by_role,
  is_own,
}) {
  const {
    trashView,
    tag,
    userid,
    path,
    isAdmin,
    setContextname,
    setContextsize,
    setContextlastmod,
    setContextdelete,
    setContextinfo,
    setContextextension,
    setContextauthor,
    setContexterror,
    setContexterrormodal,
    basePath,
    currentOrg,
    setViewerFile,
    enqueueTrashTask,
  } = useContext(ApplicationContext);
  const queryClient = useQueryClient();
  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState(name);
  const [error, setError] = useState("");
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [copied, setCopied] = useState(false);
  const [fileRenaming, setFileRenaming] = useState(false);
  const [fileNewName, setFileNewName] = useState(name);
  const [folderPickerOpen, setFolderPickerOpen] = useState(false);
  const [fileOp, setFileOp] = useState(null); // "copy" | "move"
  const [opLoading, setOpLoading] = useState(false);

  const handleCopyPath = () => {
    const s3Path = `s3://${currentOrg?.bucket_name || ""}/${keypath}`;
    navigator.clipboard.writeText(s3Path).then(() => {
      setCopied(true);
      setTimeout(() => { setCopied(false); setVisible(false); }, 800);
    });
  };

  const handleFileRename = async () => {
    if (!fileNewName || fileNewName === name) {
      setFileRenaming(false);
      return;
    }
    setOpLoading(true);
    try {
      await renameFile(currentOrg.id, keypath, fileNewName, basePath);
      queryClient.invalidateQueries(["contents"]);
      setVisible(false);
      setFileRenaming(false);
    } catch (e) {
      setError(e.message);
      setContexterror(e.message || "File rename failed.");
      setContexterrormodal(true);
    } finally {
      setOpLoading(false);
    }
  };

  const handleFolderSelect = async (targetPrefix) => {
    if (!currentOrg || !keypath) return;
    setOpLoading(true);
    try {
      if (fileOp === "copy") {
        await copyFile(currentOrg.id, keypath, targetPrefix, basePath);
      } else {
        await moveFile(currentOrg.id, keypath, targetPrefix, basePath);
      }
      queryClient.invalidateQueries(["contents"]);
      setVisible(false);
      setFolderPickerOpen(false);
    } catch (e) {
      setError(e.message);
      const fallbackMessage =
        fileOp === "copy"
          ? "Copy operation failed or was cancelled."
          : "Move operation failed or was cancelled.";
      setContexterror(e.message || fallbackMessage);
      setContexterrormodal(true);
      setFolderPickerOpen(false);
    } finally {
      setOpLoading(false);
      setFileOp(null);
    }
  };

  const canModifyFolder = () => {
    if (!currentOrg) return false;
    if (isAdmin) return true;
    if (!created_by_role || created_by_role === "admin") return false;
    return true;
  };

  const loadmetadata = async () => {
    const res = await get_metadata(`${path}${name}`, tag, basePath);
    setContextauthor(res["author"]);
  };
  const restoreitems = async () => {
    if (currentOrg && keypath) {
      try {
        await restoreFromTrash(currentOrg.id, keypath);
        queryClient.invalidateQueries(["trash"]);
        queryClient.invalidateQueries(["contents"]);
        setVisible(false);
      } catch (e) {
        setError(e.message);
      }
    } else {
      await restoreItems(keypath || `trash/${userid}/${name}`);
      setTimeout(() => {
        queryClient.invalidateQueries(["trash", userid]);
      }, 1500);
    }
  };

  const handlePurge = async () => {
    if (!currentOrg || !keypath) return;
    try {
      await purgeFromTrash(currentOrg.id, keypath);
      queryClient.invalidateQueries(["trash"]);
      setVisible(false);
    } catch (e) {
      setError(e.message);
    }
  };
  const ref = useRef(null);
  const handleRename = async () => {
    if (!newName || newName === name) {
      setRenaming(false);
      return;
    }
    try {
      await renameFolder(currentOrg.id, keypath, newName);
      queryClient.invalidateQueries(["contents"]);
      queryClient.invalidateQueries(["browse"]);
      setVisible(false);
      setRenaming(false);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleFolderDelete = () => {
    if (!currentOrg) return;
    enqueueTrashTask({
      type: "folder",
      name,
      keypath,
      orgId: currentOrg.id,
    });
    setVisible(false);
  };

  const assignContext = () => {
    setContextname(name);
    setContextsize(size);
    setContextextension(
      name.split(".").pop().toLowerCase().split(".").pop().toLowerCase()
    );
    setContextlastmod(last_modified);
  };
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setVisible((prev) => !prev);
        setRenaming(false);
      }
    };
    document.addEventListener("click", handleClickOutside, true);
    document.addEventListener("contextmenu", handleClickOutside, true);
    return () => {
      document.removeEventListener("click", handleClickOutside, true);
      document.removeEventListener("contextmenu", handleClickOutside, true);
    };
  });
  const hasMenuItems = trashView || itemType === "file" || (itemType === "folder" && canModifyFolder());

  return (
    <>
    <FolderPickerModal
      open={folderPickerOpen}
      onClose={() => { setFolderPickerOpen(false); setFileOp(null); }}
      onSelect={handleFolderSelect}
      title={fileOp === "copy" ? "Copy file to…" : "Move file to…"}
      processing={opLoading}
    />
    {visible && hasMenuItems && (
      <div ref={ref}>
        <div
          className="z-10 absolute bg-popover rounded-lg border border-border shadow-lg flex flex-col text-foreground w-56"
          style={{ left: `${left}px`, top: `${top}px` }}
        >
          {error && (
            <div className="px-3 py-1.5 text-xs text-destructive">{error}</div>
          )}

          {renaming ? (
            <div className="p-3">
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleRename();
                  if (e.key === "Escape") { setRenaming(false); setVisible(false); }
                }}
                className="w-full px-2 py-1.5 text-sm border border-border rounded bg-secondary text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
              <div className="flex gap-2 mt-2">
                <button onClick={handleRename} className="text-xs px-2 py-1 bg-accent rounded text-white">Save</button>
                <button onClick={() => { setRenaming(false); setVisible(false); }} className="text-xs px-2 py-1 bg-secondary rounded text-foreground border border-border">Cancel</button>
              </div>
            </div>
          ) : (
            <>
              {itemType === "file" && (
                <div
                  onClick={() => {
                    loadmetadata();
                    setContextinfo(true);
                    assignContext();
                    setVisible(false);
                  }}
                  className="text-foreground font-normal hover:rounded-lg hover:cursor-pointer px-3 py-2.5 m-1 rounded-md hover:bg-gray-100 flex items-center text-sm transition-colors duration-150"
                >
                  <Info className="ml-2 mr-4 w-4 h-4" strokeWidth={1.5} />
                  <p>File Information</p>
                </div>
              )}

              {itemType === "file" && isViewableFile(name) && !trashView && (
                <div
                  onClick={() => {
                    setViewerFile({ fileKey: keypath, fileName: name, size, last_modified });
                    setVisible(false);
                  }}
                  className="text-foreground font-normal hover:rounded-lg hover:cursor-pointer px-3 py-2.5 m-1 rounded-md hover:bg-gray-100 flex items-center text-sm transition-colors duration-150"
                >
                  <Eye className="ml-2 mr-4 w-4 h-4" strokeWidth={1.5} />
                  <p>View File</p>
                </div>
              )}

              {!trashView && (
                <div
                  onClick={handleCopyPath}
                  className="text-foreground font-normal hover:rounded-lg hover:cursor-pointer px-3 py-2.5 m-1 rounded-md hover:bg-gray-100 flex items-center text-sm transition-colors duration-150"
                >
                  <Copy className="ml-2 mr-4 w-4 h-4" strokeWidth={1.5} />
                  <p>{copied ? "Copied!" : "Copy Path"}</p>
                </div>
              )}

              {trashView ? (
                <>
                  <div
                    onClick={() => {
                      assignContext();
                      restoreitems();
                    }}
                    className="hover:cursor-pointer hover:rounded-lg font-normal px-3 py-2.5 m-1 rounded-md hover:bg-gray-100 flex items-center text-sm transition-colors duration-150"
                  >
                    <Image width={25} className="ml-2 mr-4" src={Restore} alt="Restore" />
                    <p>Restore</p>
                  </div>
                  {currentOrg && !confirmPurge && (
                    <div
                      onClick={() => setConfirmPurge(true)}
                      className="hover:cursor-pointer hover:rounded-lg font-normal px-3 py-2.5 m-1 rounded-md hover:bg-gray-100 flex items-center text-sm text-destructive transition-colors duration-150"
                    >
                      <Trash2 className="ml-2 mr-4 w-4 h-4" strokeWidth={1.5} />
                      <p>Permanently Delete</p>
                    </div>
                  )}
                  {confirmPurge && (
                    <div className="p-3">
                      <p className="text-xs text-destructive mb-2">
                        This cannot be undone. Delete <span className="font-semibold">{name}</span> forever?
                      </p>
                      <div className="flex gap-2">
                        <button onClick={handlePurge} className="text-xs px-2 py-1 bg-destructive text-destructive-foreground rounded">Yes, delete</button>
                        <button onClick={() => { setConfirmPurge(false); setVisible(false); }} className="text-xs px-2 py-1 bg-secondary rounded text-foreground border border-border">Cancel</button>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <>
                  {itemType === "folder" && canModifyFolder() && (
                    <>
                      <div
                        onClick={() => { setNewName(name); setRenaming(true); }}
                        className="hover:cursor-pointer hover:rounded-lg font-normal px-3 py-2.5 m-1 rounded-md hover:bg-gray-100 flex items-center text-sm transition-colors duration-150"
                      >
                        <Pencil className="ml-2 mr-4 w-4 h-4" strokeWidth={1.5} />
                        <p>Rename</p>
                      </div>
                      <div
                        onClick={handleFolderDelete}
                        className="hover:cursor-pointer hover:rounded-lg font-normal px-3 py-2.5 m-1 rounded-md hover:bg-gray-100 flex items-center text-sm text-destructive transition-colors duration-150"
                      >
                        <FolderX className="ml-2 mr-4 w-4 h-4" strokeWidth={1.5} />
                        <p>Move to Trash</p>
                      </div>
                    </>
                  )}

                  {itemType === "file" && !fileRenaming && (
                    <>
                      <div
                        onClick={() => { setFileNewName(name); setFileRenaming(true); }}
                        className="hover:cursor-pointer hover:rounded-lg font-normal px-3 py-2.5 m-1 rounded-md hover:bg-gray-100 flex items-center text-sm transition-colors duration-150"
                      >
                        <Pencil className="ml-2 mr-4 w-4 h-4" strokeWidth={1.5} />
                        <p>Rename</p>
                      </div>
                      <div
                        onClick={() => { setFileOp("copy"); setFolderPickerOpen(true); setVisible(false); }}
                        className="hover:cursor-pointer hover:rounded-lg font-normal px-3 py-2.5 m-1 rounded-md hover:bg-gray-100 flex items-center text-sm transition-colors duration-150"
                      >
                        <FolderInput className="ml-2 mr-4 w-4 h-4" strokeWidth={1.5} />
                        <p>Copy to…</p>
                      </div>
                      <div
                        onClick={() => { setFileOp("move"); setFolderPickerOpen(true); setVisible(false); }}
                        className="hover:cursor-pointer hover:rounded-lg font-normal px-3 py-2.5 m-1 rounded-md hover:bg-gray-100 flex items-center text-sm transition-colors duration-150"
                      >
                        <FolderSymlink className="ml-2 mr-4 w-4 h-4" strokeWidth={1.5} />
                        <p>Move to…</p>
                      </div>
                      <div
                        onClick={() => {
                          setContextdelete(true);
                          assignContext();
                          setVisible(false);
                        }}
                        className="hover:cursor-pointer hover:rounded-lg font-normal px-3 py-2.5 m-1 rounded-md hover:bg-gray-100 flex items-center text-sm text-destructive transition-colors duration-150"
                      >
                        <Trash2 className="ml-2 mr-4 w-4 h-4" strokeWidth={1.5} />
                        <p>Delete</p>
                      </div>
                    </>
                  )}
                  {itemType === "file" && fileRenaming && (
                    <div className="p-3">
                      <input
                        autoFocus
                        value={fileNewName}
                        onChange={(e) => setFileNewName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleFileRename();
                          if (e.key === "Escape") { setFileRenaming(false); setVisible(false); }
                        }}
                        className="w-full px-2 py-1.5 text-sm border border-border rounded bg-secondary text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                        disabled={opLoading}
                      />
                      <div className="flex gap-2 mt-2">
                        <button onClick={handleFileRename} disabled={opLoading} className="text-xs px-2 py-1 bg-accent rounded text-white disabled:opacity-50">
                          {opLoading ? "Renaming…" : "Save"}
                        </button>
                        <button onClick={() => { setFileRenaming(false); setVisible(false); }} disabled={opLoading} className="text-xs px-2 py-1 bg-secondary rounded text-foreground border border-border disabled:opacity-50">Cancel</button>
                      </div>
                      {opLoading && (
                        <p className="text-[11px] text-status-warning mt-2">
                          Please wait — do not close this window. Large files may take a moment.
                        </p>
                      )}
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>
    )}
    </>
  );
}
