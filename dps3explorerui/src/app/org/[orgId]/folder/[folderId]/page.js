"use client";
import { useEffect } from "react";
import { useParams } from "next/navigation";
import { useContext } from "react";
import { useQuery } from "react-query";
import { ApplicationContext } from "@/services/ContextProvider";
import { listAccessibleOrgs } from "@/services/browse";
import { Loader2 } from "lucide-react";

/**
 * /org/[orgId]/folder/[folderId] — sets org + folder from URL.
 * folderId is a base64url-encoded S3 prefix so slashes survive routing.
 */
export default function FolderPage() {
  const { orgId, folderId } = useParams();
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

    // Decode folderId: base64url → S3 prefix string
    let prefix = "";
    try {
      prefix = atob(folderId.replace(/-/g, "+").replace(/_/g, "/"));
    } catch {
      prefix = decodeURIComponent(folderId);
    }
    if (prefix && !prefix.endsWith("/")) prefix += "/";

    if (String(currentOrg?.id) !== String(mapped.id)) {
      setCurrentOrg(mapped);
      setBasePath(org.folder_path || org.bucket_name || "");
    }
    setTag("explorer");
    setPath(prefix);
    setKeys(prefix.replace(/\/$/, "").split("/").filter(Boolean));
    setTrashView(false);
    setStarredView(false);
  }, [orgsData, orgId, folderId]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full w-full">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return null;
}
