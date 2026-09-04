import { useContext, useEffect, useRef } from "react";
import { ApplicationContext } from "@/services/ContextProvider";

export default function Delete({ children }) {
  const ref = useRef(null);
  const {
    path,
    username,
    contextdelete,
    setContextdelete,
    contextname,
    setContextname,
    basePath,
    enqueueTrashTask,
  } = useContext(ApplicationContext);

  const moveToTrash = () => {
    enqueueTrashTask({
      type: "file",
      name: contextname,
      fileKey: `${path}${contextname}`,
      username,
      basePath,
    });
    setContextname("");
    setContextdelete(false);
  };

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setContextdelete((prev) => !prev);
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
    contextdelete && (
      <div className="fixed inset-0 bg-black/50 flex justify-center items-center z-50">
        <div
          ref={ref}
          className="flex flex-col border border-border rounded-lg bg-card shadow-lg z-10 w-2/5 max-w-md"
        >
          <div className="py-4 px-6 text-xl font-semibold text-destructive">
            Move to Trash
          </div>
          <div className="py-4 px-6 font-normal text-foreground text-sm">
            Are you sure you want to move{" "}
            <span className="font-semibold">{contextname}</span> to trash?
          </div>
          <div className="px-6 pb-2 text-xs text-muted-foreground">
            This runs in the background — you can keep working while it finishes.
          </div>
          <div className="flex flex-row-reverse py-4 px-6 gap-3">
            <button
              onClick={() => {
                setContextname("");
                setContextdelete(false);
              }}
              className="px-4 py-2 text-sm font-medium text-foreground bg-secondary rounded-lg border border-border hover:bg-gray-100 transition-colors duration-150"
            >
              Cancel
            </button>
            <button
              onClick={moveToTrash}
              className="px-4 py-2 text-sm font-medium text-white bg-delete-button-bg rounded-lg hover:opacity-90 transition-colors duration-150"
            >
              Move to Trash
            </button>
          </div>
        </div>
      </div>
    )
  );
}
