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
import Delete from "@/components/delete";
import TrashTasks from "@/components/trashtasks";
import { TaskDock } from "@/components/taskdock";
import Information from "@/components/info";
import Dialog from "@/components/dialog";
import NewFolder from "@/components/newfolder";
import FileViewerModal from "@/components/FileViewerModal";
import S3ExplorerAccessBlocked from "@/components/S3ExplorerAccessBlocked";

export default function Layout({ children }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [dragging, setDragging] = useState(false);
  const [mounted, setMounted] = useState(false);
  const {
    userid,
    setUserid,
    setUsername,
    username,
    sessionUser,
    sessionLoading,
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
  }, []);

  const hasUser = Boolean(sessionUser);

  const { data: access, isLoading: accessLoading, isError: accessError } = useQuery(
    ["explorer-access"],
    getExplorerAccess,
    {
      enabled: mounted && !sessionLoading && hasUser,
      retry: false,
      staleTime: 60 * 1000,
    },
  );

  const { data: adminMe } = useQuery(
    ["admin-me"],
    getAdminMe,
    {
      enabled: mounted && !sessionLoading && hasUser && access?.can_access === true,
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

  if (sessionLoading) {
    return (
      <div className="flex items-center justify-center h-full w-full">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!hasUser) {
    router.replace("/login");
    return null;
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
        {access && !access.can_access ? (
          <S3ExplorerAccessBlocked access={access} />
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3 px-6">
            <p className="text-foreground font-medium">Unable to load identity</p>
            <p className="text-sm text-muted-foreground text-center max-w-sm">
              Your session could not access this workspace. Please sign in again.
            </p>
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
