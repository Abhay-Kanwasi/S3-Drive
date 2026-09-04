"use client";

import { useContext, useEffect, useRef } from "react";
import { useQueryClient } from "react-query";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { ApplicationContext } from "@/services/ContextProvider";
import { deleteByFilename } from "@/services/Queries";
import { deleteFolder } from "@/services/browse";
import { DockedToast } from "./taskdock";

const AUTO_DISMISS_MS = 4000;

export default function TrashTasks() {
  const { trashTasks, setTrashTasks } = useContext(ApplicationContext);
  const queryClient = useQueryClient();
  const busy = useRef(false);

  const patchTask = (id, patch) =>
    setTrashTasks((prev) =>
      prev.map((task) => (task.id === id ? { ...task, ...patch } : task))
    );

  useEffect(() => {
    if (busy.current) return;
    const next = trashTasks.find((task) => task.status === "queued");
    if (!next) return;

    busy.current = true;
    patchTask(next.id, { status: "working" });

    (async () => {
      try {
        if (next.type === "folder") {
          await deleteFolder(next.orgId, next.keypath);
        } else {
          await deleteByFilename(
            next.username,
            next.basePath,
            next.fileKey,
            next.name
          );
        }
        patchTask(next.id, { status: "done" });
      } catch (err) {
        patchTask(next.id, {
          status: "failed",
          error: err?.message || "Move to trash failed",
        });
      } finally {
        busy.current = false;
        queryClient.invalidateQueries(["contents"]);
        queryClient.invalidateQueries(["browse"]);
        queryClient.invalidateQueries(["trash"]);
      }
    })();
  }, [trashTasks]);

  const activeCount = trashTasks.filter(
    (task) => task.status === "queued" || task.status === "working"
  ).length;
  const failed = trashTasks.filter((task) => task.status === "failed");
  const doneCount = trashTasks.filter((task) => task.status === "done").length;
  const isActive = activeCount > 0;

  useEffect(() => {
    if (isActive || trashTasks.length === 0 || failed.length > 0) return;
    const timer = setTimeout(() => setTrashTasks([]), AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [isActive, trashTasks.length, failed.length]);

  useEffect(() => {
    const onBeforeUnload = (e) => {
      if (!isActive) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [isActive]);

  if (trashTasks.length === 0) return null;

  const working = trashTasks.find((task) => task.status === "working");
  const headerText = isActive
    ? "Moving to trash"
    : failed.length > 0
      ? "Move to trash failed"
      : "Moved to trash";

  const detailText = isActive
    ? trashTasks.length > 1
      ? `${doneCount + failed.length + 1} of ${trashTasks.length} · ${working?.name || ""}`
      : working?.name || ""
    : failed.length > 0
      ? failed[0].error
      : `${doneCount} item(s) moved to trash`;

  return (
    <DockedToast>
      <div className="flex items-start gap-2 rounded-lg border border-border bg-card shadow-lg px-3 py-2 max-w-[calc(100vw-4rem)]">
        {isActive ? (
          <Loader2 className="w-4 h-4 mt-0.5 shrink-0 animate-spin text-accent" />
        ) : failed.length > 0 ? (
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0 text-destructive" />
        ) : (
          <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0 text-custom-green" />
        )}
        <div className="min-w-0 text-sm">
          <div className="font-medium text-foreground">{headerText}</div>
          <div
            className={`text-xs truncate ${failed.length > 0 && !isActive ? "text-destructive" : "text-muted-foreground"}`}
          >
            {detailText}
          </div>
        </div>
        {!isActive && (
          <button
            onClick={() => setTrashTasks([])}
            className="px-2 py-1 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-gray-100 transition-colors"
          >
            Close
          </button>
        )}
      </div>
    </DockedToast>
  );
}
