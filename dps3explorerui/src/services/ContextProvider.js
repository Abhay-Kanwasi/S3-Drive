"use client";
import { createContext, useState, useEffect } from "react";
import { getSelectedUserId, setSelectedUserId as persistUserId } from "@/services/auth";
import { useTheme } from "@/hooks/useTheme";

export const ApplicationContext = createContext(null);

export function ContextProvider({ children }) {
  const { theme, toggleTheme } = useTheme();
  const [folder, setFolder] = useState("");
  const [userid, setUserid] = useState();
  const [username, setUsername] = useState();
  const [currentUserId, setCurrentUserIdState] = useState("");

  useEffect(() => {
    const stored = getSelectedUserId();
    if (stored) {
      setCurrentUserIdState(stored);
      setUserid(Number(stored));
    }
  }, []);

  const setCurrentUserId = (userId) => {
    const id = userId == null ? "" : String(userId).trim();
    persistUserId(id || null);
    setCurrentUserIdState(id);
    if (id && /^\d+$/.test(id)) {
      setUserid(Number(id));
    }
  };

  const [path, setPath] = useState("");
  const [basePath, setBasePath] = useState("");
  const [trashView, setTrashView] = useState(false);
  const [starredView, setStarredView] = useState(false);
  const [recentView, setRecentView] = useState(false);
  const [trashpath, setTrashPath] = useState("");
  const [keys, setKeys] = useState([]);
  const [card, setCard] = useState(true);
  const [files, setFiles] = useState([]);
  const [duplicates, setDuplicates] = useState([]);
  const [uploadsafe, setUploadsafe] = useState({});
  const [progress, setProgress] = useState({});
  const [contextfolder, setContextfolder] = useState("");
  const [contextname, setContextname] = useState("");
  const [contextsize, setContextsize] = useState("");
  const [contextlastmod, setContextlastmod] = useState("");
  const [contextextension, setContextextension] = useState("");
  const [contextauthor, setContextauthor] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [currentOrg, setCurrentOrg] = useState(null);
  const [tag, setTag] = useState("");
  const [contexterror, setContexterror] = useState("");
  const [contextdelete, setContextdelete] = useState(false);
  const [contextnew, setContextnew] = useState(false);
  const [contextinfo, setContextinfo] = useState(false);
  const [contexterrormodal, setContexterrormodal] = useState(false);
  const [viewerFile, setViewerFile] = useState(null);
  const [trashTasks, setTrashTasks] = useState([]);

  const enqueueTrashTask = (task) => {
    setTrashTasks((prev) => [
      ...prev,
      {
        ...task,
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        status: "queued",
        error: "",
      },
    ]);
  };

  return (
    <ApplicationContext.Provider
      value={{
        userid,
        setUserid,
        username,
        setUsername,
        currentUserId,
        setCurrentUserId,
        folder,
        setFolder,
        path,
        setPath,
        keys,
        setKeys,
        card,
        setCard,
        files,
        setFiles,
        uploadsafe,
        setUploadsafe,
        progress,
        setProgress,
        contextname,
        setContextname,
        contextsize,
        setContextsize,
        contextlastmod,
        setContextlastmod,
        contextdelete,
        setContextdelete,
        contextinfo,
        setContextinfo,
        contexterrormodal,
        setContexterrormodal,
        contexterror,
        setContexterror,
        contextextension,
        setContextextension,
        contextauthor,
        setContextauthor,
        duplicates,
        setDuplicates,
        trashpath,
        setTrashPath,
        trashView,
        setTrashView,
        starredView,
        setStarredView,
        recentView,
        setRecentView,
        contextnew,
        setContextnew,
        contextfolder,
        setContextfolder,
        isAdmin,
        setIsAdmin,
        currentOrg,
        setCurrentOrg,
        tag,
        setTag,
        basePath,
        setBasePath,
        viewerFile,
        setViewerFile,
        trashTasks,
        setTrashTasks,
        enqueueTrashTask,
        theme,
        toggleTheme,
      }}
    >
      {children}
    </ApplicationContext.Provider>
  );
}
