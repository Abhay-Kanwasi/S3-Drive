import { useMutation, useQueryClient } from "react-query";
import { useContext, useEffect, useRef, useState } from "react";
import { deleteByFilename } from "@/services/Queries";
import { ApplicationContext } from "@/services/ContextProvider";

export default function Delete({ children }) {
  const queryClient = useQueryClient();
  const ref = useRef(null);
  const [error, setError] = useState("");
  const [processing, setProcessing] = useState(false);
  const {
    userid,
    path,
    username,
    contextdelete,
    setContextdelete,
    contextname,
    setContextname,
    basePath,
  } = useContext(ApplicationContext);
  const invalidate = () => {
    setError("");
    setProcessing(true);
    deleteMutation.mutate(contextname);
  };
  const deleteMutation = useMutation({
    mutationFn: (contextname) =>
      deleteByFilename(
        username,
        basePath,
        `${path}${contextname}`,
        contextname,
      ),
    onSuccess: () => {
      setProcessing(false);
      queryClient.refetchQueries(["contents", path]);
      setContextname("");
      setContextdelete(false);
    },
    onError: (err) => {
      setProcessing(false);
      setError(err.message || "Failed to delete file");
    },
  });
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
          {error && (
            <div className="px-6 pb-2 text-xs text-destructive">{error}</div>
          )}
          {processing && (
            <div className="px-6 pb-2 text-xs text-amber-600">
              Moving to trash — please wait, do not close this window...
            </div>
          )}
          <div className="flex flex-row-reverse py-4 px-6 gap-3">
            <button
              onClick={() => {
                if (processing) return;
                setError("");
                setContextname("");
                setContextdelete(false);
              }}
              disabled={processing}
              className="px-4 py-2 text-sm font-medium text-foreground bg-secondary rounded-lg border border-border hover:bg-accent transition-colors duration-150 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={invalidate}
              disabled={processing}
              className="px-4 py-2 text-sm font-medium text-white bg-delete-button-bg rounded-lg hover:opacity-90 transition-colors duration-150 disabled:opacity-50"
            >
              {processing ? "Moving..." : "Move to Trash"}
            </button>
          </div>
        </div>
      </div>
    )
  );
}
