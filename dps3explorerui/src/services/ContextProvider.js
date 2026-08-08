"use client";
import { createContext, useState, useEffect } from "react";

export const ApplicationContext = createContext(null);

export function ContextProvider({ children }) {
  const [folder, setFolder] = useState("");
  const [userid, setUserid] = useState();
  const [username, setUsername] = useState();
  const [authToken, setAuthToken] = useState("");

  useEffect(() => {
    const stored = localStorage.getItem("authToken");
    if (stored) setAuthToken(stored);
  }, []);
  const [path, setPath] = useState("");
  const [basePath, setBasePath] = useState("");
  const [trashView, setTrashView] = useState(false);
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

  return (
    <ApplicationContext.Provider
      value={{
        userid,
        setUserid,
        username,
        setUsername,
        authToken,
        setAuthToken,
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
      }}
    >
      {children}
    </ApplicationContext.Provider>
  );
}
