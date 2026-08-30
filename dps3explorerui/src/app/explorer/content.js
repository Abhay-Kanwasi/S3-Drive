"use client";
import Breadcrumb from "@/components/Breadcrumb";
import Upload from "@/components/upload";
import View from "@/components/view";
import ToggleView from "@/components/toggleview";
import NotificationBell from "@/components/NotificationBell";
import SearchBar from "@/components/SearchBar";
import UserMenu from "@/components/UserMenu";
import { useContext } from "react";
import { ApplicationContext } from "@/services/ContextProvider";
import { useMutation } from "react-query";
import { loadContents } from "@/services/Queries";

export default function Content({ children }) {
  const { card, keys, setKeys, setPath, basePath, currentOrg, username, userid, isAdmin } = useContext(ApplicationContext);

  const folderMutation = useMutation({
    mutationFn: (p) => loadContents(p, basePath, currentOrg?.id),
  });

  // Build breadcrumb path items from keys array
  const breadcrumbPath = keys.map((key, index) => ({
    id: keys.slice(0, index + 1).join("/") + "/",
    name: key,
  }));

  const handleNavigate = (id) => {
    if (!id) {
      setKeys([]);
      setPath(basePath || "");
      folderMutation.mutate(basePath || "");
      return;
    }
    const targetPath = id.endsWith("/") ? id : id + "/";
    const parts = targetPath.replace(/\/$/, "").split("/").filter(Boolean);
    setKeys(parts);
    setPath(targetPath);
    folderMutation.mutate(targetPath);
  };

  const user = { name: username || String(userid || ""), email: "", avatarUrl: "" };
  // BACKEND REQUIRED: GET /api/search?q=&orgId= — search not yet available

  return (
    <div className="bg-background flex-1 h-full overflow-y-auto flex flex-col">
      {/* Top bar */}
      <div className="flex flex-row items-center gap-3 px-5 py-3 border-b border-border bg-background sticky top-0 z-20">
        <div className="flex-1 min-w-0">
          <Breadcrumb path={breadcrumbPath} onNavigate={handleNavigate} />
        </div>
        {isAdmin && (
          <div className="hidden md:block w-56">
            <SearchBar onSearch={() => {}} scope="org" disabled />
          </div>
        )}
        <NotificationBell />
        <UserMenu user={user} />
      </div>

      {/* Action bar */}
      <div className="flex flex-row justify-end items-center px-5 py-2 border-b border-border">
        <ToggleView />
      </div>

      {/* File grid/list */}
      <div className="flex flex-row flex-wrap pb-24 px-5 pt-4">
        <View />
      </div>
      <Upload />
    </div>
  );
}
