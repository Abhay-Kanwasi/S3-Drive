import {
  getFolderContent,
  delete_by_filename,
  metadata_endpoint,
  getListofFolder,
} from "@/services/server";
import { browseFolders, listTrash, listAccessibleOrgs } from "@/services/browse";
import { getOrganizations } from "@/services/admin";

function mapOrgToBucketItem(org) {
  return {
    folder_name: org.org_name || org.name || "Organization",
    folder_path: "",
    bucket_name: org.bucket_name,
    org_id: org.id,
    org_name: org.org_name || org.name,
  };
}

/** Sidebar org list via GET /browse/orgs (grant + admin scope). */
export const loadBuckets = async () => {
  try {
    const data = await listAccessibleOrgs();
    if (Array.isArray(data)) {
      return data.map((item) =>
        item.folder_name != null ? item : mapOrgToBucketItem(item),
      );
    }
  } catch {
    // Fall back to admin org list for global admins if browse fails
  }
  try {
    const orgs = await getOrganizations();
    return (orgs || []).map(mapOrgToBucketItem);
  } catch {
    return [];
  }
};

export const loadFolderitems = async (orgId) => {
  if (orgId) {
    const data = await listTrash(orgId);
    return data.items || [];
  }
  const data = await getListofFolder();
  if (data?.content !== undefined) {
    const content = data.content.map((name) => {
      return name;
    });
    return content;
  }
  return [];
};

export const loadContents = async (rootdir, basePath, orgId) => {
  if (rootdir == "" && !orgId) return [];

  if (orgId) {
    const data = await browseFolders(orgId, rootdir);
    const combined = [];
    for (const folder of data.folders) {
      combined.push({
        name: folder.name,
        key: folder.key,
        type: "folder",
        size: 0,
        last_modified: "",
        created_by: folder.created_by,
        created_by_role: folder.created_by_role,
        is_own: folder.is_own,
      });
    }
    for (const file of data.files) {
      combined.push({
        name: file.name,
        key: file.key,
        type: "file",
        size: file.size,
        last_modified: file.last_modified,
      });
    }
    return combined;
  }

  const response = await getFolderContent(rootdir, basePath);
  const content = response?.content?.map((name) => {
    return name;
  });
  return content || [];
};

export const deleteByFilename = async (
  username,
  basePath,
  file_key,
  filename
) => {
  const response = await delete_by_filename(
    username,
    filename,
    file_key,
    basePath
  );
  return response;
};

export const get_metadata = async (file_key, tag, basePath) => {
  const response = await metadata_endpoint(file_key, tag, basePath);
  return response;
};
