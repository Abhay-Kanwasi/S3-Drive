"use client";
import { useState, useEffect, useContext } from "react";
import { ApplicationContext } from "@/services/ContextProvider";
import { browseFolders } from "@/services/browse";
import { Folder, ChevronRight, ArrowLeft, Loader2, AlertTriangle } from "lucide-react";

export default function FolderPickerModal({ open, onClose, onSelect, title = "Select destination folder", processing = false }) {
  const { currentOrg } = useContext(ApplicationContext);
  const [currentPrefix, setCurrentPrefix] = useState("");
  const [breadcrumb, setBreadcrumb] = useState([]);
  const [folders, setFolders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open && currentOrg) {
      setCurrentPrefix("");
      setBreadcrumb([]);
      loadFolders("");
    }
  }, [open, currentOrg]);

  const loadFolders = async (prefix) => {
    if (!currentOrg) return;
    setLoading(true);
    setError("");
    try {
      const data = await browseFolders(currentOrg.id, prefix);
      setFolders(data.folders || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const navigateInto = (folder) => {
    const newPrefix = folder.key;
    setCurrentPrefix(newPrefix);
    setBreadcrumb([...breadcrumb, folder.name]);
    loadFolders(newPrefix);
  };

  const navigateBack = () => {
    const parts = currentPrefix.replace(/\/$/, "").split("/");
    parts.pop();
    const newPrefix = parts.length > 0 ? parts.join("/") + "/" : "";
    setCurrentPrefix(newPrefix);
    setBreadcrumb(breadcrumb.slice(0, -1));
    loadFolders(newPrefix);
  };

  const handleSelect = () => {
    onSelect(currentPrefix);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-popover border border-border rounded-xl shadow-2xl w-[420px] max-h-[70vh] flex flex-col">
        <div className="px-5 py-4 border-b border-border">
          <h3 className="text-base font-semibold text-foreground">{title}</h3>
          <p className="text-xs text-muted-foreground mt-1">
            Navigate to the target folder then click &quot;Select&quot;.
          </p>
        </div>

        <div className="px-5 py-2 border-b border-border flex items-center gap-1 text-xs text-muted-foreground min-h-[36px]">
          <span className="font-medium text-foreground">/</span>
          {breadcrumb.map((seg, i) => (
            <span key={i} className="flex items-center gap-1">
              <ChevronRight className="w-3 h-3" />
              <span className="text-foreground">{seg.replace("/", "")}</span>
            </span>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-2 min-h-[200px]">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="flex items-center gap-2 text-destructive text-sm p-3">
              <AlertTriangle className="w-4 h-4" /> {error}
            </div>
          ) : (
            <>
              {breadcrumb.length > 0 && (
                <div
                  onClick={navigateBack}
                  className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-accent cursor-pointer text-sm text-muted-foreground"
                >
                  <ArrowLeft className="w-4 h-4" />
                  <span>Back</span>
                </div>
              )}
              {folders.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-6">No subfolders here</p>
              )}
              {folders.map((f) => (
                <div
                  key={f.key}
                  onClick={() => navigateInto(f)}
                  className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-accent cursor-pointer text-sm text-foreground"
                >
                  <Folder className="w-4 h-4 text-amber-500" />
                  <span className="truncate">{f.name}</span>
                  <ChevronRight className="w-3.5 h-3.5 ml-auto text-muted-foreground" />
                </div>
              ))}
            </>
          )}
        </div>

        <div className="px-5 py-3 border-t border-border flex items-center justify-between">
          {processing ? (
            <div className="flex items-center gap-2 text-sm text-foreground">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Processing… please wait</span>
            </div>
          ) : (
            <>
              <p className="text-xs text-muted-foreground truncate max-w-[200px]">
                Target: <span className="font-mono">/{currentPrefix || "(root)"}</span>
              </p>
              <div className="flex gap-2">
                <button
                  onClick={onClose}
                  className="px-3 py-1.5 text-sm rounded-md border border-border bg-secondary text-foreground hover:bg-accent"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSelect}
                  className="px-3 py-1.5 text-sm rounded-md bg-new-button-bg text-foreground hover:opacity-90"
                >
                  Select
                </button>
              </div>
            </>
          )}
        </div>

        <div className="px-5 py-2 border-t border-border">
          <p className="text-[11px] text-amber-600 flex items-center gap-1.5">
            <AlertTriangle className="w-3 h-3 shrink-0" />
            {processing
              ? "Operation in progress. Do not close or navigate away — large files may take several minutes."
              : "Do not close this window during large file operations. The process runs on the server and closing may leave partial copies."}
          </p>
        </div>
      </div>
    </div>
  );
}
