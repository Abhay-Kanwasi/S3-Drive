const API_HOSTNAME = process.env.NEXT_PUBLIC_HOSTNAME;
export const hostname = `${API_HOSTNAME}/explorer`;
export const CHUNK_SIZE = 14 * 1024 * 1024;

function authHeaders(extraHeaders = {}) {
  const token = typeof window !== "undefined" ? localStorage.getItem("authToken") : null;
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extraHeaders,
  };
}

export const getUploadConstraints = async () => {
  const url = `${hostname}/services/upload-constraints`;
  const response = await fetch(url, { headers: authHeaders() });
  if (!response.ok) throw new Error("Failed to fetch upload constraints");
  return response.json();
};

export const getUAMFolderContent = async () => {
  try {
    const url = `${hostname}/uam/folders`;
    const response = await fetch(url, { headers: authHeaders() });
    return response.json();
  } catch (err) {
    return Promise.resolve([]);
  }
};

export const getListofFolder = async () => {
  try {
    const url = `${hostname}/services/recycle`;
    const response = await fetch(url, { headers: authHeaders() });
    return response.json();
  } catch (err) {
    return Promise.resolve([]);
  }
};

export const restoreItems = async (path) => {
  try {
    const url = `${hostname}/services/restore?key=${path}`;
    const response = await fetch(url, { headers: authHeaders() });
    return response.json();
  } catch (err) {
    return Promise.resolve([]);
  }
};

export const checkIfFolderExists = async (foldername, basePath) => {
  try {
    const url = `${hostname}/services/event`;
    const response = await fetch(url, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        name: foldername,
        user_id: 0,
        basePath: basePath,
      }),
    });
    return response;
  } catch (err) {
    return null;
  }
};

export const createFolder = async (foldername, basePath) => {
  try {
    const url = `${hostname}/services/folders`;
    const response = await fetch(url, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        name: foldername,
        user_id: 0,
        basePath: basePath,
      }),
    });
    return response;
  } catch (err) {
    return Promise.resolve([]);
  }
};

export const getFolderContent = async (foldername, basePath) => {
  try {
    const url = `${hostname}/services/content`;
    const response = await fetch(url, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        name: foldername,
        user_id: 0,
        basePath: basePath,
      }),
    });
    return response.json();
  } catch (err) {
    return Promise.resolve([]);
  }
};

export const delete_by_filename = async (
  username,
  _filename,
  _file_key,
  basePath
) => {
  const url = `${hostname}/services/delete`;
  const response = await fetch(url, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      author: username,
      userid: "0",
      filename: _filename,
      file_key: _file_key,
      basePath: basePath,
    }),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "Delete failed");
    throw new Error(text);
  }
};

export const totalChunks = (FILE_SIZE) => {
  return FILE_SIZE % CHUNK_SIZE == 0
    ? FILE_SIZE / CHUNK_SIZE
    : Math.floor(FILE_SIZE / CHUNK_SIZE) + 1;
};

export const uploadByPart = async (
  file,
  filepath,
  _author,
  basePath,
  fileSize
) => {
  try {
    const url = `${hostname}/services/initiate`;
    const body = {
      userid: 0,
      name: filepath,
      author: _author,
      basePath: basePath,
    };
    if (fileSize != null) body.file_size = fileSize;
    const response = await fetch(url, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
    return response;
  } catch (err) {
    return Promise.resolve([]);
  }
};

export const uploadChunks = async (
  filechunk,
  uploadId,
  counter,
  filePath,
  basePath
) => {
  const formData = new FormData();
  formData.append("file", filechunk);
  formData.append("path", filePath);
  formData.append("count", String(counter));
  formData.append("tag", uploadId);
  formData.append("basePath", basePath);
  const token = localStorage.getItem("authToken");
  const url = `${hostname}/services/chunks`;
  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });
  } catch (err) {
    const message = String(err?.message || "").toLowerCase();
    if (message.includes("failed to fetch")) {
      throw new Error(
        "Upload service became unavailable while sending file chunks. Please retry."
      );
    }
    throw new Error(err?.message || `Chunk ${counter} upload failed.`);
  }

  if (!response.ok) {
    const errJson = await response.json().catch(() => ({}));
    const detail =
      errJson?.detail ||
      `Chunk ${counter} upload failed (${response.status}).`;
    throw new Error(detail);
  }

  const data = await response.json().catch(() => ({}));
  if (!data?.tag) {
    throw new Error("Chunk upload failed: missing ETag from server.");
  }
  return data;
};

export const finishUpload = async (
  file_name,
  file_author,
  filepath,
  uploadId,
  e_tags,
  basePath
) => {
  try {
    const url = `${hostname}/services/finalised`;
    const response = await fetch(url, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        filename: file_name,
        author: file_author,
        file_key: filepath,
        uploadID: uploadId,
        e_tag: e_tags,
        userid: 0,
        basePath: basePath,
      }),
    });
    return response;
  } catch (err) {
    return Promise.resolve([]);
  }
};

export const download_files = async (
  _filename,
  _file_key,
  basePath
) => {
  try {
    const url = `${hostname}/services/download?file_key=${_file_key}&filename=${_filename}&basePath=${basePath}`;
    const response = await fetch(url, { headers: authHeaders() });
    return response;
  } catch (err) {
    return Promise.resolve([]);
  }
};

export const metadata_endpoint = async (_file_key, tag, basePath) => {
  try {
    const url = `${hostname}/services/meta?file_Key=${_file_key}&tag=${tag}&basePath=${basePath}`;
    const response = await fetch(url, { headers: authHeaders() });
    return response.json();
  } catch (err) {
    return Promise.resolve([]);
  }
};

// ─── File Preview ────────────────────────────────────────────────────────────

export const VIEWABLE_EXTENSIONS = [".csv", ".xlsx", ".parquet", ".json"];

export const isViewableFile = (filename) => {
  if (!filename) return false;
  const lower = filename.toLowerCase();
  return VIEWABLE_EXTENSIONS.some((ext) => lower.endsWith(ext));
};

export const getFilePreview = async (fileKey, basePath, page = 1, pageSize = 50, sheet = null) => {
  const params = new URLSearchParams({
    file_key: fileKey,
    basePath: basePath,
    page: String(page),
    page_size: String(pageSize),
  });
  if (sheet) params.set("sheet", sheet);
  const url = `${hostname}/viewer/preview?${params}`;
  const response = await fetch(url, { headers: authHeaders() });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to load file preview");
  }
  return response.json();
};
