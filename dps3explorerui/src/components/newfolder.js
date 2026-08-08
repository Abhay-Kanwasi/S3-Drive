import { useQueryClient } from "react-query";
import { useContext, useEffect, useRef, useState } from "react";
import { checkIfFolderExists, createFolder } from "@/services/server";
import { createFolder as createFolderV2 } from "@/services/browse";
import { ApplicationContext } from "@/services/ContextProvider";

export default function NewFolder({ children }) {
  const queryClient = useQueryClient();
  const [foldervalue, setFoldervalue] = useState("");
  const [foldername, setfoldername] = useState("");
  const [disabled, setDisabled] = useState(true);
  const [error, setError] = useState("");
  const ref = useRef(null);
  const {
    path,
    contextnew,
    setContextnew,
    contextfolder,
    setContextfolder,
    userid,
    basePath,
    currentOrg,
  } = useContext(ApplicationContext);
  const invalidate = () => {
    setTimeout(() => {
      queryClient.invalidateQueries(["contents", path, currentOrg?.id]);
      queryClient.invalidateQueries(["contents"]);
      queryClient.invalidateQueries(["browse"]);
    }, 500);
  };

  const createFolderTrigger = async (name) => {
    setError("");
    try {
      if (currentOrg) {
        await createFolderV2(currentOrg.id, path, foldervalue);
      } else {
        await createFolder(name, basePath);
      }
      invalidate();
    } catch (e) {
      setError(e.message || "Failed to create folder");
      return;
    }
    setContextnew(false);
  };

  const checkFolderExists = async (e) => {
    const Path = `${path}${e.target.value}`;
    const folderName = e.target.value;
    if (folderName.length !== 0 || folderName !== undefined) {
      if (currentOrg) {
        setDisabled(false);
      } else {
        var res = await checkIfFolderExists(Path, basePath);
        setContextfolder(res.json());
        if (res.status === 200) {
          setDisabled(false);
        } else if (res.status == 400) {
          setDisabled(true);
        }
      }
    } else if (folderName.length === 0 || folderName === undefined) {
      setDisabled(true);
    }
  };

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setContextnew((prev) => !prev);
      }
    };
    document.addEventListener("click", handleClickOutside, true);
    document.addEventListener("contextmenu", handleClickOutside, true);
    return () => {
      document.removeEventListener("click", handleClickOutside, true);
      document.removeEventListener("contextmenu", handleClickOutside, true);
    };
  });
  return (
    contextnew && (
      <div className="fixed inset-0 bg-black/50 flex justify-center items-center z-50">
        <div
          ref={ref}
          className="flex flex-col rounded-lg border border-border bg-card z-10 w-2/5 max-w-md shadow-lg"
        >
          <div className="py-4 px-6 text-xl font-semibold text-foreground">
            Create New Folder
          </div>
          <div className="flex flex-col gap-4 px-6 py-3">
            {error && <p className="text-destructive text-sm">{error}</p>}
            <input
              onKeyUp={(e) => {
                if (e.target.value == "") {
                  setDisabled(true);
                } else {
                  setFoldervalue(e.target.value);
                  checkFolderExists(e);
                  setfoldername(`${path}${e.target.value}`);
                }
              }}
              placeholder="Enter folder name"
              className="flex w-full min-w-0 flex-1 resize-none overflow-hidden rounded-lg text-foreground focus:outline-0 focus:ring-1 focus:ring-ring border border-input bg-secondary h-12 placeholder:text-muted-foreground p-4 text-sm font-normal leading-normal"
            />
          </div>

          <div className="flex flex-row-reverse py-4 px-6 gap-3">
            <button
              onClick={() => {
                setContextnew(false);
                setContextfolder("");
                setError("");
                setDisabled(true);
              }}
              className="px-4 py-2 text-sm font-medium text-foreground bg-secondary rounded-lg border border-border hover:bg-accent transition-colors duration-150"
            >
              Cancel
            </button>
            <button
              disabled={disabled}
              onClick={() => {
                if (foldervalue.length !== 0) {
                  createFolderTrigger(`${foldername}/`);
                }
              }}
              className="px-4 py-2 text-sm font-medium text-foreground bg-new-button-bg rounded-lg disabled:bg-muted disabled:text-muted-foreground hover:bg-new-bg transition-colors duration-150"
            >
              Create
            </button>
          </div>
        </div>
      </div>
    )
  );
}
