"use client";
import Breadcrumb from "@/components/Breadcrumb";
import Upload from "@/components/upload";
import View from "@/components/view";
import ToggleView from "@/components/toggleview";
import NotificationBell from "@/components/NotificationBell";
import SearchBar from "@/components/SearchBar";
import UserMenu from "@/components/UserMenu";
import { useContext, useRef, useState, useEffect } from "react";
import { ApplicationContext } from "@/services/ContextProvider";
import { useMutation, useQuery } from "react-query";
import { loadContents } from "@/services/Queries";
import { getUploadConstraints } from "@/services/server";
import { Plus, FilePlus, FolderPlus } from "lucide-react";

export default function Content({ children }) {
  const { card, keys, setKeys, setPath, basePath, currentOrg, username, userid, isAdmin, path, uploadsafe, setUploadsafe, setProgress, files, setFiles, contextnew, setContextnew, setContextfolder, setContexterror, setContexterrormodal, starredView, setStarredView, recentView, setRecentView } = useContext(ApplicationContext);

  const [toggle, setToggle] = useState(false);
  const newref = useRef(null);
  const dialogref = useRef(null);

  const canCreateFolder = !currentOrg || isAdmin || (path && path !== basePath);

  const { data: constraints } = useQuery("upload-constraints", getUploadConstraints, {
    staleTime: 5 * 60 * 1000, retry: 1,
  });

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (newref.current && !newref.current.contains(e.target)) setToggle(false);
    };
    document.addEventListener("click", handleClickOutside, true);
    return () => document.removeEventListener("click", handleClickOutside, true);
  }, []);

  const handleUpload = async (e) => {
    if (!path) {
      setContexterrormodal(true);
      setContexterror("Please select a bucket first to upload files(s).");
      return;
    }
    const allowedExtensions = constraints?.allowed_extensions;
    if (!allowedExtensions) {
      setContexterrormodal(true);
      setContexterror("Unable to verify allowed file types. Please try again.");
      return;
    }
    const _files = [];
    let safeObj = {};
    for (let _file of e.target.files) {
      const nameLower = _file.name.toLowerCase();
      const isAllowed = allowedExtensions.some((ext) => nameLower.endsWith(ext));
      if (isAllowed) {
        _files.push({ data: _file, completed: false, progress: 0 });
        setProgress((prev) => ({ ...prev, [_file.name]: 0 }));
        safeObj = { ...safeObj, [_file.name]: { locked: false, progress: 0, data: _file } };
      } else {
        setContexterrormodal(true);
        setContexterror(`File type not supported. Allowed: ${allowedExtensions.join(", ")}`);
      }
    }
    if (_files.length) {
      setUploadsafe({ ...uploadsafe, ...safeObj });
      setFiles([..._files]);
    }
  };

  const folderMutation = useMutation({
    mutationFn: (p) => loadContents(p, basePath, currentOrg?.id),
  });

  // Build breadcrumb path items from keys array
  const breadcrumbPath = starredView
    ? [{ id: "Starred/", name: "Starred" }]
    : recentView
    ? [{ id: "Recent/", name: "Recent" }]
    : keys.map((key, index) => ({
        id: keys.slice(0, index + 1).join("/") + "/",
        name: key,
      }));

  const handleNavigate = (id) => {
    if (starredView && String(id || "").replace(/\/$/, "") === "Starred") {
      return;
    }
    if (recentView && String(id || "").replace(/\/$/, "") === "Recent") {
      return;
    }
    setStarredView(false);
    setRecentView(false);
    if (!id) {
      setKeys([]);
      setPath(basePath || "");
      folderMutation.mutate(basePath || "");
      return;
    }
    const targetPath = id.endsWith("/") ? id : id + "/";
    const parts = targetPath.replace(/\/$/, "").split("/").filter(Boolean);
    setKeys(parts);
    setPath(targetPath);
    folderMutation.mutate(targetPath);
  };

  const user = { name: username || String(userid || ""), email: "", avatarUrl: "" };
  // BACKEND REQUIRED: GET /api/search?q=&orgId= — search not yet available

  return (
    <div className="bg-background flex-1 h-full overflow-y-auto flex flex-col">
      {/* Top bar */}
      <div className="flex flex-row items-center gap-3 px-5 py-3 border-b border-border bg-background sticky top-0 z-20">
        <div className="flex-1 min-w-0">
          <Breadcrumb path={breadcrumbPath} onNavigate={handleNavigate} />
        </div>
        {isAdmin && (
          <div className="hidden md:block w-56">
            <SearchBar onSearch={() => {}} scope="org" disabled />
          </div>
        )}
        <NotificationBell />
        <UserMenu user={user} />
      </div>

      {/* Action bar */}
      <div className="flex flex-row justify-end items-center px-5 py-2 border-b border-border">
        <ToggleView />
      </div>

      {/* File grid/list */}
      <div className="flex flex-row flex-wrap pb-24 px-5 pt-4">
        <View />
      </div>
      <Upload />

      {/* Floating New button */}
      {!starredView && !recentView && (
      <div
        ref={newref}
        onClick={() => setToggle((v) => !v)}
        className="fixed bottom-8 right-8 z-50 bg-accent text-white rounded-full shadow-elevated cursor-pointer hover:-translate-y-0.5 hover:bg-accent-hover transition-all duration-200 ease-out"
      >
        <div className="flex items-center px-5 py-3 gap-2">
          <Plus strokeWidth={2} className={`h-5 w-5 transition-transform duration-200 ${toggle ? "rotate-45" : ""}`} />
          <span className="font-medium text-sm">New</span>
        </div>

        <div
          onClick={(e) => e.stopPropagation()}
          className={`absolute bottom-full right-0 mb-2 w-48 border border-gray-200 bg-white rounded-xl shadow-elevated p-1 text-foreground origin-bottom-right transition-all duration-200 ease-out ${toggle ? "opacity-100 scale-100 translate-y-0" : "pointer-events-none opacity-0 scale-95 translate-y-2"}`}
        >
          <p
            onClick={() => {
              if (!isAdmin && (!path || path.length === 0)) {
                setContexterrormodal(true);
                setContexterror("Please navigate into a folder to upload files.");
              } else {
                dialogref.current.click();
              }
            }}
            className="text-foreground font-normal hover:cursor-pointer px-3 py-2.5 m-1 rounded-md hover:bg-gray-100 flex items-center text-sm"
          >
            <FilePlus className="mr-3 w-4 h-4" strokeWidth={1.5} />
            File Upload
            <input
              type="file"
              multiple
              ref={dialogref}
              className="hidden"
              accept=".csv, .txt, .xlsx, .xlsb, .xlsm, .tsv"
              onClick={(e) => { e.target.value = null; }}
              onChange={handleUpload}
            />
          </p>
          {canCreateFolder && (
            <div
              onClick={() => {
                if (!isAdmin && (!path || path.length === 0)) {
                  setContexterrormodal(true);
                  setContexterror("Please navigate into a folder to create subfolders.");
                } else {
                  setToggle(false);
                  setContextnew(true);
                  setContextfolder("");
                }
              }}
              className="text-foreground font-normal hover:cursor-pointer px-3 py-2.5 m-1 rounded-md hover:bg-gray-100 flex items-center text-sm"
            >
              <FolderPlus className="mr-3 w-4 h-4" strokeWidth={1.5} />
              New folder
            </div>
          )}
        </div>
      </div>
      )}
    </div>
  );
}
