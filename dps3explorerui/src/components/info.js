import Image from "next/image";
import { useContext, useEffect, useRef } from "react";
import FolderIcon from "../app/assets/folder.svg";
import { ApplicationContext } from "@/services/ContextProvider";
import { get_metadata } from "@/services/Queries";
import { X } from "lucide-react";

export default function Information({ children }) {
  const {
    path,
    contextinfo,
    setContextinfo,
    contextname,
    contextsize,
    contextlastmod,
    contextextension,
    contextauthor,
    setContextauthor,
  } = useContext(ApplicationContext);
  const ref = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setContextinfo((prev) => !prev);
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
    contextinfo && (
      <div className="fixed inset-0 bg-black/50 flex justify-center items-center z-50">
        <div
          ref={ref}
          className="flex flex-col border border-border rounded-lg bg-card z-10 w-1/3 max-w-lg shadow-lg"
        >
          <div className="inline-flex justify-between py-4 px-6 text-xl font-semibold">
            <p className="text-foreground mt-2">File Information</p>
            <button
              onClick={() => {
                setContextinfo(false);
                setContextauthor("");
              }}
              className="cursor-pointer text-muted-foreground hover:text-foreground transition-colors duration-150 p-1 rounded-md hover:bg-accent"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <div className="ml-5 my-3">
            <Image className="px-3 my-3" src={FolderIcon} alt="Folder" />
          </div>
          <div className="flex flex-col ml-5 mb-6 text-foreground">
            <div className="py-2 px-4 inline-flex flex-col">
              <div className="text-foreground text-sm font-medium leading-normal">
                Name
              </div>
              <div className="text-muted-foreground text-sm font-normal leading-normal line-clamp-2">
                {contextname}
              </div>
            </div>
            <div className="py-2 px-4 inline-flex flex-col">
              <div className="text-foreground text-sm font-medium leading-normal">
                Type
              </div>
              <div className="text-muted-foreground text-sm font-normal leading-normal line-clamp-2">
                {contextextension}
              </div>
            </div>
            <div className="py-2 px-4 inline-flex flex-col">
              <div className="text-foreground text-sm font-medium leading-normal">
                Size
              </div>
              <div className="text-muted-foreground text-sm font-normal leading-normal line-clamp-2">
                {contextsize}
              </div>
            </div>
            <div className="py-2 px-4 inline-flex flex-col">
              <div className="text-foreground text-sm font-medium leading-normal">
                Author
              </div>
              <div className="text-muted-foreground text-sm font-normal leading-normal line-clamp-2">
                {contextauthor}
              </div>
            </div>
            <div className="py-2 px-4 inline-flex flex-col">
              <div className="text-foreground text-sm font-medium leading-normal">
                Last modified
              </div>
              <div className="text-muted-foreground text-sm font-normal leading-normal line-clamp-2">
                {contextlastmod}
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  );
}
