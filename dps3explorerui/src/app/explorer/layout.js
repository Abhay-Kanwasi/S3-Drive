"use client";
import { useContext, useEffect, useState } from "react";
import { useQueryClient, useQuery } from "react-query";
import { Loader2 } from "lucide-react";
import Sidebar from "./sidebar";
import Content from "./content";
import DragAndDrop from "@/components/dnd";
import { ApplicationContext } from "@/services/ContextProvider";
import { hostname, getUploadConstraints } from "@/services/server";
import { getExplorerAccess } from "@/services/access";
import Delete from "@/components/delete";
import Information from "@/components/info";
import Dialog from "@/components/dialog";
import NewFolder from "@/components/newfolder";
import FileViewerModal from "@/components/FileViewerModal";
import S3ExplorerAccessBlocked from "@/components/S3ExplorerAccessBlocked";

export default function Layout({ children }) {
  const queryClient = useQueryClient();
  const [dragging, setDragging] = useState(false);
  const [userdata, setUserdata] = useState({});
  const [mounted, setMounted] = useState(false);

  const {
    userid,
    setUserid,
    setUsername,
    setAuthToken,
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
    authToken,
  } = useContext(ApplicationContext);

  const { data: access, isLoading: accessLoading } = useQuery(
    "explorer-access",
    getExplorerAccess,
    {
      enabled: mounted,
      retry: false,
      staleTime: 60 * 1000,
    },
  );

  useEffect(() => {
    if (access?.id && !userid) {
      setUserid(access.id);
      if (access.user_name) setUsername(access.user_name);
    }
  }, [access]);

  const { data: constraints } = useQuery("upload-constraints", getUploadConstraints, {
    staleTime: 5 * 60 * 1000,
    retry: 1,
    enabled: mounted && access?.can_access === true,
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
    // var _duplicates = [];
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
        // _duplicates.push(_file.name);
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

  const checkAdminStatus = async (token) => {
    try {
      const res = await fetch(`${hostname}/uam/items`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        const hasAdmin = Array.isArray(data) && data.some((item) => item.url_path === "/admin");
        setIsAdmin(hasAdmin);
      }
    } catch (e) {
      // non-critical
    }
  };

  const initializeUser = (userData) => {
    if (userData && userData.userId) {
      setUserdata(userData);
      setUserid(userData.userId);
      setUsername(userData.userName);
      if (userData.token) {
        localStorage.setItem("authToken", userData.token);
        setAuthToken(userData.token);
        checkAdminStatus(userData.token);
      } else {
        const storedToken = localStorage.getItem("authToken");
        if (storedToken) checkAdminStatus(storedToken);
      }
    }
  };

  useEffect(() => {
    // Cross-origin: receive auth data from parent app via postMessage
    const allowedOrigins = [
      "https://green.datapoem.ai",
      "https://qa.datapoem.ai",
      "https://devapp.datapoem.ai",
      "https://qaapp.datapoem.ai",
      "https://app.datapoem.ai",
      "https://insights.datapoem.ai",
      "http://localhost:8080",
    ];
    const handleMessage = (event) => {
      if (!allowedOrigins.includes(event.origin)) return;
      if (event.data?.type === "AUTH_USER_DATA" && event.data.payload) {
        localStorage.setItem("userData", JSON.stringify(event.data.payload));
        initializeUser(event.data.payload);
      }
    };
    window.addEventListener("message", handleMessage);

    // Tell parent we're ready
    if (window.parent !== window) {
      window.parent.postMessage({ type: "EXPLORER_READY" }, "*");
    }

    // Fallback: check localStorage (same-origin or already received data)
    var _user = JSON.parse(localStorage.getItem("userData"));
    if (_user != null) {
      initializeUser(_user);
    } else {
      const storedToken = localStorage.getItem("authToken");
      if (storedToken) checkAdminStatus(storedToken);
    }

    return () => window.removeEventListener("message", handleMessage);
  }, []);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return <div className="h-full w-full bg-background" aria-hidden="true" />;
  }

  if (accessLoading) {
    return (
      <div className="flex items-center justify-center h-full w-full">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (access && !access.can_access) {
    return <S3ExplorerAccessBlocked access={access} />;
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
      className="flex flex-row h-full w-full overflow-hidden"
    >
      {dragging ? (
        <DragAndDrop />
      ) : (
        <>
          {/* <Header /> */}
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
              basePath={basePath}
              onClose={() => setViewerFile(null)}
            />
          )}
        </>
      )}
    </div>
  );
}
