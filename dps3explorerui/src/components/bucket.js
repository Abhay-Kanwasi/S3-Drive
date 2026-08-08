"use client";
import { useQuery } from "react-query";
import { loadBuckets } from "../services/Queries";
import { useContext } from "react";
import { ApplicationContext } from "@/services/ContextProvider";
import { ChevronRight } from "lucide-react";

export function BucketItem({ children }) {
  const {
    userid,
    tag,
    setTag,
    setPath,
    keys,
    setKeys,
    setTrashView,
    setBasePath,
    setCurrentOrg,
  } = useContext(ApplicationContext);
  const bucket = useQuery(["buckets", userid], () => loadBuckets());
  if (bucket.isLoading)
    return (
      <div className="rounded-lg p-4 max-w-sm w-full mx-auto">
        <div className="animate-pulse flex flex-col space-y-6 py-2">
          <div className="h-2 items-center bg-muted w-full rounded"></div>
          <div className="h-2 items-center bg-muted w-full rounded"></div>
        </div>
      </div>
    );
  if (bucket.isSuccess && Array.isArray(bucket.data))
    return (
      <div className="text-sidebar-foreground">
        {bucket.data.map((items, index) => (
          <div
            className="flex flex-row rounded-lg text-sm items-center gap-2 cursor-pointer hover:bg-new-bg-light hover:text-foreground px-4 py-2.5 mt-1 transition-colors duration-150"
            key={index}
            onClick={() => {
              setTag("explorer");
              setPath(items.folder_path);
              setKeys([items.folder_name]);
              setBasePath(items.folder_path || items.bucket_name);
              setTrashView(false);
              setCurrentOrg(
                items.org_id
                  ? { id: items.org_id, bucket_name: items.bucket_name, org_name: items.org_name }
                  : null
              );
            }}
          >
            <span>
              <ChevronRight className="w-4 h-4" />
            </span>
            {items.folder_name}
          </div>
        ))}
      </div>
    );
}
