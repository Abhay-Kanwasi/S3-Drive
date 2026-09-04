import Image from "next/image";
import { useQueryClient, useQuery } from "react-query";
import { useContext, useEffect, useState } from "react";
import { ApplicationContext } from "@/services/ContextProvider";
import UploadIcon from "../app/assets/upload.svg";
import MinIcon from "../app/assets/Minus.svg";
import {
  uploadByPart,
  totalChunks,
  uploadChunks,
  CHUNK_SIZE,
  finishUpload,
  getUploadConstraints,
} from "@/services/server";
import { DockedToast } from "./taskdock";

const FALLBACK_MAX_BYTES = 5 * 1024 * 1024 * 1024;
const ACTIVE_UPLOAD_STATUSES = new Set(["queued", "uploading"]);

function isCancellationError(err) {
  const message = String(err?.message || "").toLowerCase();
  return err?.name === "AbortError" || message.includes("cancel");
}

function buildIssueSummary(cancelledCount, failedCount) {
  if (cancelledCount > 0 && failedCount > 0) {
    return `${cancelledCount} upload(s) cancelled and ${failedCount} failed.`;
  }
  if (cancelledCount > 0) {
    return `${cancelledCount} upload(s) cancelled.`;
  }
  if (failedCount > 0) {
    return `${failedCount} upload(s) failed.`;
  }
  return "";
}

export default function Upload() {
  const {
    files,
    setFiles,
    path,
    username,
    progress,
    setProgress,
    setContexterror,
    setContexterrormodal,
    basePath,
    isAdmin,
  } = useContext(ApplicationContext);
  const queryClient = useQueryClient();
  const [visible, setVisible] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [uploaded, setUploaded] = useState(false);
  const [fileStates, setFileStates] = useState({});
  const [isUploading, setIsUploading] = useState(false);

  const { data: constraints } = useQuery("upload-constraints", getUploadConstraints, {
    staleTime: 60 * 1000,
    retry: 1,
  });

  const allowedExtensions = constraints?.allowed_extensions;
  const maxUploadBytes = constraints?.max_upload_bytes || FALLBACK_MAX_BYTES;

  const isAllowedFile = (filename) => {
    if (!allowedExtensions) return false;
    const lower = filename.toLowerCase();
    if (lower.endsWith(".csv.gz")) return true;
    return allowedExtensions.some((ext) => lower.endsWith(ext));
  };

  const setFileState = (filename, patch) => {
    setFileStates((prev) => ({
      ...prev,
      [filename]: { ...(prev[filename] || {}), ...patch },
    }));
  };

  const resetPanel = () => {
    setProgress({});
    setFileStates({});
    setVisible(false);
    setMinimized(false);
    setUploaded(false);
  };

  const filesUpload = async (files) => {
    if (isUploading) return;

    if (!isAdmin && !path) {
      setContexterrormodal(true);
      setContexterror("Please select a bucket first to upload files(s).");
      return;
    }
    if (!allowedExtensions) {
      setContexterrormodal(true);
      setContexterror("Unable to verify allowed file types. Please try again.");
      return;
    }

    const _files = files;
    const rejected = _files.filter((f) => !isAllowedFile(f.data.name));
    if (rejected.length > 0) {
      setContexterrormodal(true);
      setContexterror(
        `File type not allowed: ${rejected.map((f) => f.data.name).join(", ")}. Accepted formats: ${allowedExtensions.join(", ")}`
      );
      setIsUploading(false);
      return;
    }

    const oversized = _files.filter((f) => f.data.size > maxUploadBytes);
    if (oversized.length > 0) {
      setContexterrormodal(true);
      const limitDisplay = maxUploadBytes >= 1024 * 1024 * 1024
        ? `${(maxUploadBytes / (1024 ** 3)).toFixed(1)} GB`
        : `${(maxUploadBytes / (1024 ** 2)).toFixed(0)} MB`;
      setContexterror(
        `File too large: ${oversized.map((f) => f.data.name).join(", ")}. Maximum allowed size: ${limitDisplay}`
      );
      setIsUploading(false);
      return;
    }

    const initialProgress = {};
    const initialStates = {};
    _files.forEach((f) => {
      initialProgress[f.data.name] = 0;
      initialStates[f.data.name] = { status: "queued", progress: 0, error: "" };
    });

    setProgress((prev) => ({ ...prev, ...initialProgress }));
    setFileStates((prev) => ({ ...prev, ...initialStates }));
    setUploaded(false);
    setVisible(true);
    setMinimized(false);
    setIsUploading(true);

    let cancelledCount = 0;
    let failedCount = 0;

    for (let _f of _files) {
      const filename = _f.data.name;
      setFileState(filename, { status: "uploading", progress: 0, error: "" });

      try {
        const response = await uploadByPart(
          filename,
          `${path}${filename}`,
          username,
          basePath,
          _f.data.size
        );
        if (!response || typeof response.json !== "function" || !response.ok) {
          let errMsg = "Upload initiation failed.";
          if (response && typeof response.json === "function") {
            const errBody = await response.json().catch(() => ({}));
            errMsg = errBody.detail || errMsg;
          }
          throw new Error(errMsg);
        }

        const responseBody = await response.json();
        if (!responseBody?.UploadId) {
          throw new Error("Upload initiation failed.");
        }
        const uploadId = responseBody.UploadId;

        let COUNTER = 0;
        const parts = [];
        const TOTAL_CHUNKS = totalChunks(_f.data.size);

        while (COUNTER !== TOTAL_CHUNKS) {
          const chunkStart = COUNTER * CHUNK_SIZE;
          const chunkEnd = Math.min(chunkStart + CHUNK_SIZE, _f.data.size);
          const fileChunk = _f.data.slice(chunkStart, chunkEnd);

          const chunkResponse = await uploadChunks(
            fileChunk,
            uploadId,
            COUNTER + 1,
            `${path}${filename}`,
            basePath
          );

          if (!chunkResponse || !chunkResponse.tag) {
            throw new Error("Upload was interrupted while sending chunks.");
          }

          parts.push({ ETag: chunkResponse.tag, PartNumber: COUNTER + 1 });
          COUNTER += 1;

          const percentage = Math.round((COUNTER / TOTAL_CHUNKS) * 100);
          setProgress((prev) => ({ ...prev, [filename]: percentage }));
          setFileState(filename, { status: "uploading", progress: percentage });
        }

        const final = await finishUpload(
          filename,
          username,
          `${path}${filename}`,
          uploadId,
          parts,
          basePath
        );

        if (!final || typeof final.status !== "number" || final.status !== 200) {
          let finalError = "Upload completion failed.";
          if (final && typeof final.json === "function") {
            const errBody = await final.json().catch(() => ({}));
            finalError = errBody.detail || finalError;
          }
          throw new Error(finalError);
        }

        setProgress((prev) => ({ ...prev, [filename]: 100 }));
        setFileState(filename, { status: "completed", progress: 100, error: "" });
      } catch (err) {
        const cancelled = isCancellationError(err);
        if (cancelled) cancelledCount += 1;
        else failedCount += 1;

        setFileState(filename, {
          status: cancelled ? "cancelled" : "failed",
          error: err?.message || "Upload failed",
        });
      }
    }

    queryClient.invalidateQueries("contents");
    setUploaded(true);
    setFiles([]);
    setIsUploading(false);

    const issueSummary = buildIssueSummary(cancelledCount, failedCount);
    if (issueSummary) {
      setContexterrormodal(true);
      setContexterror(`${issueSummary} Keep the upload panel open (or reopen it) to see details.`);
    }
  };

  useEffect(() => {
    if (files.length !== 0) {
      filesUpload(files);
    }
  }, [files]);

  const fileNames = Object.keys(fileStates);
  const activeCount = fileNames.filter((name) =>
    ACTIVE_UPLOAD_STATUSES.has(fileStates[name]?.status)
  ).length;
  const failedCount = fileNames.filter(
    (name) =>
      fileStates[name]?.status === "failed" || fileStates[name]?.status === "cancelled"
  ).length;
  const hasActiveUploads = activeCount > 0;
  const averageProgress =
    fileNames.length === 0
      ? 0
      : Math.round(
          fileNames.reduce((sum, name) => sum + (progress[name] || 0), 0) / fileNames.length
        );

  useEffect(() => {
    const onBeforeUnload = (e) => {
      if (!hasActiveUploads) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [hasActiveUploads]);

  const headerText = hasActiveUploads
    ? "Uploading file(s)"
    : failedCount > 0
      ? "Upload completed with issues"
      : uploaded
        ? "Uploaded successfully"
        : "Upload progress";

  const summaryText = hasActiveUploads
    ? `${activeCount} file(s) in progress`
    : failedCount > 0
      ? `${failedCount} file(s) need attention`
      : "All uploads completed";

  return (
    <>
      {visible && minimized && (
        <DockedToast>
          <div className="flex items-center gap-2 rounded-lg border border-border bg-card shadow-lg px-3 py-2 max-w-[calc(100vw-4rem)]">
            <button
              onClick={() => setMinimized(false)}
              className="text-left text-sm text-foreground hover:text-foreground/80 transition-colors"
            >
              <div className="font-medium">{headerText}</div>
              <div className="text-xs text-muted-foreground">
                {hasActiveUploads
                  ? `${averageProgress}% complete`
                  : failedCount > 0
                    ? "Click to review"
                    : "Click to close"}
              </div>
            </button>
            {!hasActiveUploads && (
              <button
                onClick={resetPanel}
                className="px-2 py-1 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-gray-100 transition-colors"
              >
                Close
              </button>
            )}
          </div>
        </DockedToast>
      )}

      {visible && !minimized && (
      <div className="fixed inset-0 bg-black/50 flex justify-center items-center z-50">
        <div className="bg-card z-10 h-96 w-2/5 max-w-lg rounded-lg border border-border shadow-lg">
          <div className="flex flex-row justify-between pl-4 py-5">
            {failedCount > 0 ? (
              <div className="inline-flex gap-x-3 font-normal text-status-warning text-xl">
                <Image src={UploadIcon} alt="Upload icon" />
                {headerText}
              </div>
            ) : uploaded ? (
              <div className="inline-flex gap-x-3 font-normal text-custom-green text-xl">
                <Image src={UploadIcon} alt="Upload icon" />
                {headerText}
              </div>
            ) : (
              <div className="inline-flex gap-x-3 font-normal text-foreground text-xl">
                <Image src={UploadIcon} alt="Upload icon" />
                {headerText}
              </div>
            )}

            <button
              onClick={() => {
                if (hasActiveUploads) {
                  setMinimized(true);
                  return;
                }
                resetPanel();
              }}
              className="mr-3 px-2 rounded-md font-semibold text-muted-foreground hover:text-foreground hover:bg-gray-100 transition-colors duration-150"
              title={hasActiveUploads ? "Minimize uploads" : "Close"}
            >
              <Image width={25} src={MinIcon} alt="Minimize" />
            </button>
          </div>
          <div className="px-7 pb-2 text-xs text-muted-foreground">
            {summaryText}
          </div>

          <div className="flex flex-row mx-3 px-4 py-3 border-dashed h-3/4 border-2 border-border rounded-lg">
            <div className="inline-flex flex-col w-full overflow-auto text-foreground">
              {Object.keys(fileStates).map((data, index) => {
                const state = fileStates[data] || {};
                const fileProgress = progress[data] || 0;
                const status = state.status || "queued";
                const statusLabel =
                  status === "completed"
                    ? "Completed"
                    : status === "failed"
                      ? state.error || "Failed"
                      : status === "cancelled"
                        ? state.error || "Cancelled"
                        : `${fileProgress}%`;

                return (
                  <div className="pb-4 px-2" key={index}>
                    <div className="pr-1 flex w-full font-normal text-sm justify-between gap-2">
                      <span className="truncate">{data}</span>
                      <span
                        className={`text-xs ${
                          status === "completed"
                            ? "text-custom-green"
                            : status === "failed" || status === "cancelled"
                              ? "text-destructive"
                              : "text-muted-foreground"
                        }`}
                      >
                        {statusLabel}
                      </span>
                    </div>
                    <div className="h-2 flex flex-col justify-center text-center transition duration-500 bg-muted rounded-full">
                      <div
                        className={`h-2 rounded-full ${
                          status === "completed"
                            ? "bg-custom-green"
                            : status === "failed" || status === "cancelled"
                              ? "bg-destructive"
                              : "bg-accent"
                        }`}
                        style={{ width: `${fileProgress}%` }}
                      ></div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
      )}
    </>
  );
}
