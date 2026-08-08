"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "react-query";
import {
  X, Folder, ChevronRight, Loader2, FolderOpen,
} from "lucide-react";
import { getFolderTree, createGrant } from "@/services/admin";

export default function FolderMappingModal({ groupId, orgId, onClose }) {
  const queryClient = useQueryClient();
  const [currentPrefix, setCurrentPrefix] = useState("");
  const [breadcrumb, setBreadcrumb] = useState([{ name: "Root", prefix: "" }]);
  const [selectedPrefix, setSelectedPrefix] = useState(null);
  const [accessLevel, setAccessLevel] = useState("read");
  const [error, setError] = useState("");

  const { data, isLoading } = useQuery(
    ["folder-tree", orgId, currentPrefix],
    () => getFolderTree(orgId, currentPrefix),
    { enabled: !!orgId },
  );

  const mutation = useMutation(
    () => createGrant(groupId, { prefix: selectedPrefix, access_level: accessLevel }),
    {
      onSuccess: () => {
        queryClient.invalidateQueries(["group-detail", groupId]);
        onClose();
      },
      onError: (err) => setError(err.message),
    },
  );

  const drillInto = (folder) => {
    setCurrentPrefix(folder.prefix);
    setBreadcrumb((prev) => [...prev, { name: folder.name, prefix: folder.prefix }]);
    setSelectedPrefix(null);
  };

  const navigateBreadcrumb = (index) => {
    const target = breadcrumb[index];
    setCurrentPrefix(target.prefix);
    setBreadcrumb((prev) => prev.slice(0, index + 1));
    setSelectedPrefix(null);
  };

  const selectFolder = (folder) => {
    setSelectedPrefix(
      selectedPrefix === folder.prefix ? null : folder.prefix,
    );
  };

  const selectCurrentAsTarget = () => {
    setSelectedPrefix(currentPrefix || "/");
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[80vh] flex flex-col">
        <div className="px-6 py-4 border-b border-border flex items-center justify-between">
          <h3 className="text-base font-semibold text-foreground">Map Folder</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-6 py-3 border-b border-border">
          <div className="flex items-center gap-1 text-xs text-muted-foreground overflow-x-auto">
            {breadcrumb.map((b, i) => (
              <span key={i} className="flex items-center gap-1 flex-shrink-0">
                {i > 0 && <ChevronRight className="w-3 h-3" />}
                <button
                  onClick={() => navigateBreadcrumb(i)}
                  className={`hover:text-foreground transition-colors ${
                    i === breadcrumb.length - 1 ? "text-foreground font-medium" : ""
                  }`}
                >
                  {b.name}
                </button>
              </span>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-3">
          {isLoading ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
            </div>
          ) : data?.folders?.length > 0 ? (
            <div className="space-y-0.5">
              {currentPrefix && (
                <button
                  onClick={selectCurrentAsTarget}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors ${
                    selectedPrefix === currentPrefix
                      ? "bg-new-bg-light ring-1 ring-new-button-bg"
                      : "hover:bg-new-bg-light/50"
                  }`}
                >
                  <FolderOpen className="w-4 h-4 text-muted-foreground flex-shrink-0" strokeWidth={1.5} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground">
                      Select this folder
                    </p>
                    <p className="text-xs text-muted-foreground font-mono truncate">{currentPrefix}</p>
                  </div>
                </button>
              )}
              {data.folders.map((f) => (
                <div
                  key={f.prefix}
                  className={`flex items-center gap-2 rounded-lg transition-colors ${
                    selectedPrefix === f.prefix
                      ? "bg-new-bg-light ring-1 ring-new-button-bg"
                      : "hover:bg-new-bg-light/50"
                  }`}
                >
                  <button
                    onClick={() => selectFolder(f)}
                    className="flex-1 flex items-center gap-3 px-3 py-2.5 text-left"
                  >
                    <Folder className="w-4 h-4 text-muted-foreground flex-shrink-0" strokeWidth={1.5} />
                    <span className="text-sm text-foreground">{f.name}</span>
                  </button>
                  <button
                    onClick={() => drillInto(f)}
                    className="px-2 py-2.5 text-muted-foreground hover:text-foreground"
                    title="Open folder"
                  >
                    <ChevronRight className="w-4 h-4" strokeWidth={1.5} />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-10">
              <Folder className="w-8 h-8 text-muted-foreground mx-auto mb-2" strokeWidth={1} />
              <p className="text-sm text-muted-foreground">No subfolders here</p>
              {currentPrefix && (
                <button
                  onClick={selectCurrentAsTarget}
                  className={`mt-3 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    selectedPrefix === currentPrefix
                      ? "bg-new-button-bg text-foreground"
                      : "border border-border text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Select this folder
                </button>
              )}
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-border space-y-3">
          {selectedPrefix && (
            <div>
              <p className="text-xs text-muted-foreground mb-2">
                Selected: <span className="font-mono text-foreground">{selectedPrefix}</span>
              </p>
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="access"
                    value="read"
                    checked={accessLevel === "read"}
                    onChange={() => setAccessLevel("read")}
                    className="accent-new-button-bg"
                  />
                  <span className="text-sm text-foreground">Read</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="access"
                    value="read_write"
                    checked={accessLevel === "read_write"}
                    onChange={() => setAccessLevel("read_write")}
                    className="accent-new-button-bg"
                  />
                  <span className="text-sm text-foreground">Read & Write</span>
                </label>
              </div>
            </div>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground">
              Cancel
            </button>
            <button
              onClick={() => mutation.mutate()}
              disabled={!selectedPrefix || mutation.isLoading}
              className="flex items-center gap-2 px-4 py-2 bg-new-button-bg rounded-lg text-sm font-semibold text-foreground hover-button disabled:opacity-50"
            >
              {mutation.isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
              Map Folder
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
