"use client";
import { useQueryClient } from "react-query";
import { useContext } from "react";
import { ApplicationContext } from "@/services/ContextProvider";
import { Trash2 } from "lucide-react";

export default function Trash() {
  const queryClient = useQueryClient();
  const {
    setTag,
    userid,
    setTrashPath,
    setTrashView,
    trashView,
    setStarredView,
    setRecentView,
    setPath,
    setKeys,
    currentOrg,
  } = useContext(ApplicationContext);

  const handleClick = () => {
    setTag("trash");
    setTrashView(true);
    if (setStarredView) setStarredView(false);
    if (setRecentView) setRecentView(false);
    if (currentOrg) {
      setPath("");
      setKeys(["Recycle bin"]);
      setTrashPath(currentOrg.id);
      queryClient.invalidateQueries(["trash"]);
    } else {
      setPath(`${String(userid)}/`);
      setTrashPath(userid);
      setKeys(["Recycle bin"]);
      queryClient.invalidateQueries(["trash", userid]);
    }
  };

  return (
    <div className="select-none">
      <button
        type="button"
        onClick={handleClick}
        className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm rounded-md transition-colors group ${
          trashView
            ? "bg-gray-100 text-foreground font-medium"
            : "text-muted-foreground hover:text-foreground hover:bg-gray-100"
        }`}
      >
        <Trash2 className={`w-4 h-4 shrink-0 transition-colors ${trashView ? "text-foreground" : "text-muted-foreground group-hover:text-foreground"}`} strokeWidth={1.5} />
        <span>Recycle bin</span>
      </button>
    </div>
  );
}
