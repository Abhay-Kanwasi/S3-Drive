"use client";
import { useEffect } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useContext } from "react";
import { useQuery } from "react-query";
import { ApplicationContext } from "@/services/ContextProvider";
import { listAccessibleOrgs } from "@/services/browse";
import { Loader2 } from "lucide-react";

/**
 * /org/[orgId] — sets the active org from the URL, then renders the explorer.
 * Accepts an optional ?path= query param to open a specific folder directly.
 */
export default function OrgPage() {
  const { orgId } = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const {
    currentOrg, setCurrentOrg,
    setPath, setKeys, setBasePath, setTag, setTrashView, setStarredView,
  } = useContext(ApplicationContext);

  const { data: orgsData, isLoading } = useQuery("accessible-orgs", listAccessibleOrgs, {
    staleTime: 60_000, retry: false,
  });

  useEffect(() => {
    if (!orgsData || !orgId) return;
    const org = orgsData.find((o) => String(o.org_id ?? o.id) === String(orgId));
    if (!org) return;
    const mapped = {
      id: org.org_id ?? org.id,
      bucket_name: org.bucket_name,
      org_name: org.org_name || org.folder_name || org.name,
    };
    // ?path= from landing page folder click takes priority over org default
    const pathParam = searchParams.get("path");
    const resolvedPath = pathParam ?? org.folder_path ?? "";
    const resolvedKeys = pathParam
      ? pathParam.replace(/\/$/, "").split("/").filter(Boolean)
      : org.folder_name ? [org.folder_name] : [];

    // Only update if org actually changed to avoid re-render loops
    if (String(currentOrg?.id) !== String(mapped.id)) {
      setCurrentOrg(mapped);
      setTag("explorer");
      setPath(resolvedPath);
      setKeys(resolvedKeys);
      setBasePath(org.folder_path || org.bucket_name || "");
      setTrashView(false);
      setStarredView(false);
    }
  }, [orgsData, orgId]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full w-full">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Render nothing — the explorer layout.js wraps this and renders Sidebar + Content
  return null;
}
