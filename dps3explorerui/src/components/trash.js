import Image from "next/image";
import { useQuery, useQueryClient } from "react-query";
import { useContext } from "react";
import { ApplicationContext } from "@/services/ContextProvider";
import { loadFolderitems } from "../services/Queries";
import { listTrash } from "@/services/browse";
import TrashSVG from "../app/assets/Trash.svg";

export default function Trash() {
  const queryClient = useQueryClient();
  const { setTag, userid, setTrashPath, setTrashView, setPath, setKeys, currentOrg } =
    useContext(ApplicationContext);

  return (
    <div className="text-sidebar-foreground select-none">
      <hr className="border-sidebar-border" />
      <div
        className="flex flex-row rounded-lg truncate text-sm items-center gap-x-1.5 cursor-pointer hover:bg-new-bg-light hover:text-foreground px-6 py-3 mt-1.5 transition-colors duration-150"
        onClick={() => {
          setTag("trash");
          setTrashView(true);
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
        }}
      >
        <Image src={TrashSVG} alt="Trash Icon" />
        Recycle bin
      </div>
    </div>
  );
}
