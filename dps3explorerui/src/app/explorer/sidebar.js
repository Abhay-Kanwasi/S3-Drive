"use client";
import { useContext, useState, useEffect, useRef } from "react";
import { useMutation, useQuery } from "react-query";
import { BucketItem } from "@/components/bucket";
import { ApplicationContext } from "@/services/ContextProvider";
import { getUploadConstraints } from "@/services/server";
import Trash from "@/components/trash";
import { Plus, FolderPlus, FilePlus, Settings } from "lucide-react";
import { useRouter } from "next/navigation";

export default function Sidebar({ children }) {
  const {
    files,
    setFiles,
    path,
    basePath,
    uploadsafe,
    setUploadsafe,
    setProgress,
    contextnew,
    setContextnew,
    setContexterror,
    setContexterrormodal,
    setContextfolder,
    isAdmin,
    currentOrg,
  } = useContext(ApplicationContext);
  const [toggle, setToggle] = useState(false);
  const canCreateFolder = !currentOrg || isAdmin || (path && path !== basePath);
  const newref = useRef(null);
  const dialogref = useRef(null);
  const router = useRouter();
  const { data: constraints } = useQuery("upload-constraints", getUploadConstraints, {
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const handleUpload = async (e) => {
    if (!path) {
      setContexterrormodal(true);
      setContexterror("Please select a bucket first to upload files(s).");
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
    for (let _file of e.target.files) {
      const nameLower = _file.name.toLowerCase();
      const isAllowed = allowedExtensions.some((ext) => nameLower.endsWith(ext));
      if (isAllowed) {
        let _fileObj = { data: _file, completed: false, progress: 0 };
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
    if (_files.length != 0) {
      let _uploadsafe = { ...uploadsafe, ...safeObj };
      setUploadsafe(_uploadsafe);
      setFiles([..._files]);
    }
  };
  useEffect(() => {
    const handleClickOutsideupload = (e) => {
      if (newref.current && !newref.current.contains(e.target)) {
        setToggle((prev) => !prev);
      }
    };
    document.addEventListener("click", handleClickOutsideupload, true);
    document.addEventListener("mousedown", handleClickOutsideupload, true);
    return () => {
      document.removeEventListener("click", handleClickOutsideupload, true);
      document.removeEventListener("mousedown", handleClickOutsideupload, true);
    };
  });
  return (
    <div className="bg-sidebar flex-shrink-0 w-64 h-full flex flex-col z-10 border-r border-sidebar-border">
      <div className="flex flex-col px-4 mx-2 pt-6 flex-1 overflow-y-auto">
        <div
          onClick={() => {
            setToggle(true);
          }}
          className="relative bg-new-button-bg flex shadow-sm mx-4 rounded-lg text-foreground font-semibold hover-button cursor-pointer"
        >
          <div className="flex items-center">
            <Plus strokeWidth={2} className="mr-3 mx-7 my-2.5" />
            <p className="font-medium my-2.5 mr-8">New</p>
          </div>

          {toggle && (
            <div
              ref={newref}
              className="border border-border text-sm w-44 absolute top-full left-0 mt-1 text-foreground divide-y divide-border bg-popover rounded-lg shadow-lg z-20"
            >
              <p
                onClick={() => {
                  if (!isAdmin && (!path || path.length === 0)) {
                    setContexterrormodal(true);
                    setContexterror(
                      "Please navigate into a folder to upload files."
                    );
                  } else {
                    dialogref.current.click();
                  }
                }}
                className="text-foreground font-normal hover:cursor-pointer px-3 py-2.5 m-1 rounded-md hover:bg-accent flex items-center text-sm"
              >
                <FilePlus className="mr-3 w-4 h-4" strokeWidth={1.5} />
                File Upload
                <input
                  type="file"
                  multiple
                  ref={dialogref}
                  className="hidden"
                  id="file-picker"
                  accept=".csv, .txt, .xlsx, .xlsb, .xlsm, .tsv"
                  onClick={(e) => {
                    const val = e.target;
                    val.value = null;
                  }}
                  onChange={(e) => {
                    handleUpload(e);
                  }}
                />
              </p>
              {canCreateFolder && (
                <div
                  onClick={() => {
                    if (!isAdmin && (!path || path.length === 0)) {
                      setContexterrormodal(true);
                      setContexterror(
                        "Please navigate into a folder to create subfolders."
                      );
                    } else {
                      setToggle(false);
                      setContextnew(true);
                      setContextfolder("");
                    }
                  }}
                  className="text-foreground font-normal hover:cursor-pointer px-3 py-2.5 m-1 rounded-md hover:bg-accent flex items-center text-sm"
                >
                  <FolderPlus className="mr-3 w-4 h-4" strokeWidth={1.5} />
                  New folder
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex pt-6 text-sidebar-foreground font-semibold text-sm pl-4 border-t border-sidebar-border mt-4">
          Organisation(s)
        </div>
        <BucketItem />
      </div>
      <div className="flex-shrink-0 px-4 mx-2 pb-4 space-y-2">
        <Trash />
        {isAdmin && (
          <button
            onClick={() => router.push("/admin")}
            className="w-full flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
          >
            <Settings className="w-4 h-4" strokeWidth={1.5} />
            Admin Panel
          </button>
        )}
      </div>
    </div>
  );
}
