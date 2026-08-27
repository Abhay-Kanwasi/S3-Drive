"use client";
import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "react-query";
import { Loader2, Plus, X, Save, HardDrive, Palette } from "lucide-react";
import { getPlatformSettings, updatePlatformSettings } from "@/services/admin";
import { useAdminMe } from "../AdminContext";

const SIZE_PRESETS = [
  { label: "1 GB", bytes: 1 * 1024 * 1024 * 1024 },
  { label: "2 GB", bytes: 2 * 1024 * 1024 * 1024 },
  { label: "5 GB", bytes: 5 * 1024 * 1024 * 1024 },
  { label: "10 GB", bytes: 10 * 1024 * 1024 * 1024 },
  { label: "20 GB", bytes: 20 * 1024 * 1024 * 1024 },
  { label: "50 GB", bytes: 50 * 1024 * 1024 * 1024 },
];

export default function PlatformSettingsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { me } = useAdminMe();
  const isGlobalAdmin = me?.is_global_admin;

  useEffect(() => {
    if (me && !isGlobalAdmin) {
      router.replace("/admin/groups");
    }
  }, [me, isGlobalAdmin, router]);

  const { data: settings, isLoading } = useQuery(
    "platform-settings",
    getPlatformSettings,
    { enabled: !!isGlobalAdmin }
  );

  const [extensions, setExtensions] = useState([]);
  const [newExt, setNewExt] = useState("");
  const [newColor, setNewColor] = useState("#6b7280");
  const [maxBytes, setMaxBytes] = useState(5 * 1024 * 1024 * 1024);
  const [dirty, setDirty] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");
  const [editingColorIdx, setEditingColorIdx] = useState(null);
  const colorPickerRef = useRef(null);

  useEffect(() => {
    if (settings) {
      const exts = (settings.allowed_extensions || []).map((item) => {
        if (typeof item === "object" && item.ext) return item;
        return { ext: String(item), color: "#6b7280" };
      });
      setExtensions(exts);
      setMaxBytes(settings.max_upload_bytes || 5 * 1024 * 1024 * 1024);
      setDirty(false);
    }
  }, [settings]);

  useEffect(() => {
    function handleClickOutside(e) {
      if (colorPickerRef.current && !colorPickerRef.current.contains(e.target)) {
        setEditingColorIdx(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const mutation = useMutation(updatePlatformSettings, {
    onSuccess: () => {
      queryClient.invalidateQueries("platform-settings");
      queryClient.invalidateQueries("upload-constraints");
      setDirty(false);
      setSuccessMsg("Settings saved successfully");
      setTimeout(() => setSuccessMsg(""), 3000);
    },
  });

  const handleAddExtension = () => {
    let ext = newExt.trim().toLowerCase();
    if (!ext) return;
    if (!ext.startsWith(".")) ext = `.${ext}`;
    if (extensions.some((e) => e.ext === ext)) {
      setNewExt("");
      return;
    }
    setExtensions([...extensions, { ext, color: newColor }]);
    setNewExt("");
    setNewColor("#6b7280");
    setDirty(true);
  };

  const handleRemoveExtension = (idx) => {
    if (extensions.length <= 1) return;
    setExtensions(extensions.filter((_, i) => i !== idx));
    setDirty(true);
  };

  const handleColorChange = (idx, color) => {
    const updated = [...extensions];
    updated[idx] = { ...updated[idx], color };
    setExtensions(updated);
    setDirty(true);
  };

  const handleSizeChange = (bytes) => {
    setMaxBytes(bytes);
    setDirty(true);
  };

  const handleSave = () => {
    mutation.mutate({
      allowed_extensions: extensions,
      max_upload_bytes: maxBytes,
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-xl font-semibold text-foreground">Platform Settings</h2>
          <p className="text-xs text-muted-foreground mt-1">
            Configure upload restrictions for all users across the platform.
          </p>
        </div>
        <button
          onClick={handleSave}
          disabled={!dirty || mutation.isLoading}
          className="flex items-center gap-2 px-4 py-2 bg-accent rounded-lg text-sm font-semibold text-white hover-button disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none"
        >
          {mutation.isLoading ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Save className="w-3.5 h-3.5" strokeWidth={2} />
          )}
          Save Changes
        </button>
      </div>

      {successMsg && (
        <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-sm text-green-700 font-medium">{successMsg}</p>
        </div>
      )}

      {mutation.isError && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm text-red-700">{mutation.error?.message}</p>
        </div>
      )}

      {/* Allowed File Formats */}
      <section className="mb-8">
        <div className="border border-border rounded-lg overflow-hidden">
          <div className="bg-gray-50 px-5 py-3 border-b border-border">
            <h3 className="text-sm font-semibold text-foreground">Allowed File Formats</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Only files with these extensions can be uploaded. Click the color dot to change the icon color.
            </p>
          </div>
          <div className="p-5">
            <div className="flex flex-wrap gap-2 mb-4">
              {extensions.map((entry, idx) => (
                <span
                  key={entry.ext}
                  className="relative inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-100 border border-border rounded-md text-xs font-medium text-foreground"
                >
                  <button
                    onClick={() => setEditingColorIdx(editingColorIdx === idx ? null : idx)}
                    className="w-3.5 h-3.5 rounded-full border border-border/50 shrink-0 cursor-pointer hover:scale-125 transition-transform"
                    style={{ backgroundColor: entry.color }}
                    title="Change color"
                  />
                  {entry.ext}
                  <button
                    onClick={() => handleRemoveExtension(idx)}
                    disabled={extensions.length <= 1}
                    className="ml-0.5 text-muted-foreground hover:text-red-500 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                    title="Remove"
                  >
                    <X className="w-3 h-3" strokeWidth={2.5} />
                  </button>

                  {editingColorIdx === idx && (
                    <div
                      ref={colorPickerRef}
                      className="absolute top-full left-0 mt-1 z-50 bg-white border border-border rounded-lg shadow-lg p-3"
                    >
                      <input
                        type="color"
                        value={entry.color}
                        onChange={(e) => handleColorChange(idx, e.target.value)}
                        className="w-10 h-10 cursor-pointer border-none p-0 rounded"
                      />
                      <p className="text-[10px] text-muted-foreground mt-1 text-center">
                        {entry.color}
                      </p>
                    </div>
                  )}
                </span>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={newExt}
                onChange={(e) => setNewExt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAddExtension();
                  }
                }}
                placeholder="e.g. .avro"
                className="w-32 px-3 py-2 border border-border rounded-lg text-sm text-foreground focus:outline-none focus:border-accent placeholder:text-muted-foreground/50"
              />
              <div className="flex items-center gap-1.5 px-2 py-1.5 border border-border rounded-lg">
                <Palette className="w-3.5 h-3.5 text-muted-foreground" />
                <input
                  type="color"
                  value={newColor}
                  onChange={(e) => setNewColor(e.target.value)}
                  className="w-6 h-6 cursor-pointer border-none p-0 rounded"
                  title="Pick icon color"
                />
              </div>
              <button
                onClick={handleAddExtension}
                disabled={!newExt.trim()}
                className="flex items-center gap-1.5 px-3 py-2 bg-accent rounded-lg text-sm font-medium text-white hover-button disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none"
              >
                <Plus className="w-3.5 h-3.5" strokeWidth={2} />
                Add
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Maximum Upload Size */}
      <section className="mb-8">
        <div className="border border-border rounded-lg overflow-hidden">
          <div className="bg-gray-50 px-5 py-3 border-b border-border">
            <div className="flex items-center gap-2">
              <HardDrive className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
              <div>
                <h3 className="text-sm font-semibold text-foreground">Maximum Upload Size</h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  The maximum file size any user can upload in a single operation.
                </p>
              </div>
            </div>
          </div>
          <div className="p-5">
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
              {SIZE_PRESETS.map((preset) => (
                <button
                  key={preset.bytes}
                  onClick={() => handleSizeChange(preset.bytes)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    maxBytes === preset.bytes
                      ? "bg-gray-100 border-accent text-foreground"
                      : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/30"
                  }`}
                >
                  {preset.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-3">
              Current limit: <span className="font-medium text-foreground">{formatBytes(maxBytes)}</span>
            </p>
          </div>
        </div>
      </section>

      {settings?.updated_at && (
        <p className="text-xs text-muted-foreground">
          Last updated: {new Date(settings.updated_at).toLocaleString()}
        </p>
      )}
    </div>
  );
}

function formatBytes(bytes) {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 ** 3)).toFixed(1)} GB`;
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 ** 2)).toFixed(0)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}
