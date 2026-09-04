"use client";
import { useContext, useEffect, useState } from "react";
import { useQueryClient, useQuery } from "react-query";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import Sidebar from "./sidebar";
import Content from "./content";
import DragAndDrop from "@/components/dnd";
import { ApplicationContext } from "@/services/ContextProvider";
import { getUploadConstraints } from "@/services/server";
import { getExplorerAccess } from "@/services/access";
import { getAdminMe } from "@/services/admin";
import { getSelectedUserId, setSelectedUserId } from "@/services/auth";
import Delete from "@/components/delete";
import TrashTasks from "@/components/trashtasks";
import { TaskDock } from "@/components/taskdock";
import Information from "@/components/info";
import Dialog from "@/components/dialog";
import NewFolder from "@/components/newfolder";
import FileViewerModal from "@/components/FileViewerModal";
import S3ExplorerAccessBlocked from "@/components/S3ExplorerAccessBlocked";

function DevUserSelector({ initialValue, onSaved }) {
  const [value, setValue] = useState(initialValue || "");

  const handleSave = () => {
    const id = String(value || "").trim();
    if (!id || !/^\d+$/.test(id)) {
      alert("Enter a numeric user id");
      return;
    }
    setSelectedUserId(id);
    onSaved?.(id);
    window.location.reload();
  };

  return (
    <div className="flex flex-col items-center justify-center h-full w-full gap-4 px-6 bg-background">
      <div className="w-full max-w-sm border border-border rounded-xl p-6 bg-white shadow-sm space-y-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-status-warning mb-1">
            Temporary · Dev only
          </p>
          <h1 className="text-lg font-semibold text-foreground">Dev user selector</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Stand-in for real auth. Requests send this id as the{" "}
            <code className="text-xs bg-muted px-1 rounded">X-User-Id</code> header.
          </p>
        </div>
        <label className="block text-sm font-medium text-foreground">
          User ID
          <input
            type="text"
            inputMode="numeric"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="e.g. 1"
            className="mt-1.5 w-full px-3 py-2 border border-border rounded-lg text-sm outline-none focus:ring-1 focus:ring-ring"
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSave();
            }}
          />
        </label>
        <button
          type="button"
          onClick={handleSave}
          className="w-full px-4 py-2 bg-accent rounded-lg text-sm font-semibold text-white hover-button"
        >
          Save &amp; reload
        </button>
      </div>
    </div>
  );
}

function DevUserBar({ currentUserId, username }) {
  const [draft, setDraft] = useState(String(currentUserId || ""));
  const [open, setOpen] = useState(false);

  const handleSave = () => {
    const id = String(draft || "").trim();
    if (!id || !/^\d+$/.test(id)) {
      alert("Enter a numeric user id");
      return;
    }
    setSelectedUserId(id);
    window.location.reload();
  };

  return (
    <div className="absolute top-2 right-2 z-30">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-[11px] px-2.5 py-1 rounded-md border border-status-warning/50 bg-status-warning-bg text-status-warning font-medium shadow-sm"
        title="Temporary identity stand-in"
      >
        Dev user: {username || currentUserId}
      </button>
      {open && (
        <div className="mt-1 w-56 rounded-lg border border-border bg-white p-3 shadow-lg space-y-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-status-warning">
            Change user id
          </p>
          <input
            type="text"
            inputMode="numeric"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="w-full px-2 py-1.5 border border-border rounded text-sm outline-none"
          />
          <button
            type="button"
            onClick={handleSave}
            className="w-full px-2 py-1.5 bg-accent rounded text-xs font-semibold"
          >
            Save &amp; reload
          </button>
        </div>
      )}
    </div>
  );
}

export default function Layout({ children }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [dragging, setDragging] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [selectedId, setSelectedId] = useState(null);

  const {
    userid,
    setUserid,
    setUsername,
    username,
    currentUserId,
    setCurrentUserId,
    isAdmin,
    setIsAdmin,
    files,
    setFiles,
    path,
    uploadsafe,
    setUploadsafe,
    progress,
    setProgress,
    setContexterror,
    setContexterrormodal,
    viewerFile,
    setViewerFile,
    basePath,
    currentOrg,
  } = useContext(ApplicationContext);

  useEffect(() => {
    setMounted(true);
    const id = getSelectedUserId();
    setSelectedId(id);
    if (id) setCurrentUserId(id);
  }, []);

  const hasUser = Boolean(selectedId);

  const { data: access, isLoading: accessLoading, isError: accessError } = useQuery(
    ["explorer-access", selectedId],
    getExplorerAccess,
    {
      enabled: mounted && hasUser,
      retry: false,
      staleTime: 60 * 1000,
    },
  );

  const { data: adminMe } = useQuery(
    ["admin-me", selectedId],
    getAdminMe,
    {
      enabled: mounted && hasUser && access?.can_access === true,
      retry: false,
      staleTime: 5 * 60 * 1000,
    },
  );

  useEffect(() => {
    if (access?.id) {
      setUserid(access.id);
      if (access.user_name) setUsername(access.user_name);
    }
  }, [access]);

  useEffect(() => {
    if (adminMe) {
      const isAdminUser = Boolean(adminMe.is_global_admin || adminMe.role_label === "admin" || adminMe.is_admin);
      setIsAdmin(isAdminUser);
      if (adminMe.user_name) setUsername(adminMe.user_name);
    } else if (access && !accessError) {
      if (access.is_admin != null) setIsAdmin(Boolean(access.is_admin));
    }
  }, [adminMe, access, accessError]);

  const { data: constraints } = useQuery("upload-constraints", getUploadConstraints, {
    staleTime: 5 * 60 * 1000,
    retry: 1,
    enabled: mounted && hasUser && access?.can_access === true,
  });

  const handleUpload = async (e) => {
    if (!isAdmin && (!path || path.length === 0)) {
      setContexterrormodal(true);
      setContexterror(
        "Please navigate into a folder to upload files."
      );
      return;
    }
    var _files = [];
    var safeObj = {};
    if (!constraints?.allowed_extensions) {
      setContexterrormodal(true);
      setContexterror("Unable to verify allowed file types. Please try again.");
      return;
    }
    const allowedExtensions = constraints.allowed_extensions;
    for (let _file of e.dataTransfer.files) {
      const nameLower = _file.name.toLowerCase();
      const isAllowed = allowedExtensions.some((ext) => nameLower.endsWith(ext));
      if (isAllowed) {
        let _fileObj = {
          data: _file,
          completed: false,
          progress: 0,
        };
        _files.push(_fileObj);
        setProgress((prev) => ({ ...prev, [_file.name]: 0 }));
        safeObj = {
          ...safeObj,
          [_file.name]: { locked: false, progress: 0, data: _file },
        };
      } else {
        setContexterrormodal(true);
        setContexterror(`File type not supported. Allowed: ${allowedExtensions.join(", ")}`);
      }
    }
    let _uploadsafe = { ...uploadsafe, ...safeObj };
    setUploadsafe(_uploadsafe);
    setFiles([...files, ..._files]);

    queryClient.invalidateQueries(["contents", path]);
  };

  if (!mounted) {
    return <div className="h-full w-full bg-background" aria-hidden="true" />;
  }

  if (!hasUser) {
    return <DevUserSelector initialValue="" />;
  }

  if (accessLoading) {
    return (
      <div className="flex items-center justify-center h-full w-full">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (accessError || (access && !access.can_access)) {
    return (
      <div className="relative h-full w-full">
        <DevUserBar currentUserId={selectedId} username={username} />
        {access && !access.can_access ? (
          <S3ExplorerAccessBlocked access={access} />
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3 px-6">
            <p className="text-foreground font-medium">Unable to load identity</p>
            <p className="text-sm text-muted-foreground text-center max-w-sm">
              Check that user id {selectedId} exists and is active, then try another id.
            </p>
            <DevUserSelector initialValue={selectedId || ""} />
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        handleUpload(e);
      }}
      className="relative flex flex-row h-full w-full overflow-hidden"
    >
      <DevUserBar currentUserId={currentUserId || selectedId} username={username || userid} />
      <TaskDock />
      <TrashTasks />
      {dragging ? (
        <DragAndDrop />
      ) : (
        <>
          <Sidebar />
          <Content />
          <Delete />
          <Information />
          <Dialog />
          <NewFolder />
          {viewerFile && (
            <FileViewerModal
              fileKey={viewerFile.fileKey}
              fileName={viewerFile.fileName}
              fileSize={viewerFile.size}
              fileLastModified={viewerFile.last_modified}
              basePath={basePath}
              orgId={currentOrg?.id}
              onClose={() => setViewerFile(null)}
            />
          )}
        </>
      )}
    </div>
  );
}
